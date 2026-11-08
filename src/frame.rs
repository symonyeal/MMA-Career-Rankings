//! Parquet shell: columns in as plain vectors, columns out as a table.
//!
//! Dates are days since 1970-01-01 (`Day`); missing floats are NaN, missing
//! strings are empty, missing days/optional integers are `None`. Required
//! integers and booleans reject nulls. Pandas wrote every snapshot
//! date as a midnight `timestamp[us]`, and `Table` writes them back the same way.

use std::fs::File;
use std::path::Path;
use std::sync::Arc;

use arrow::array::{
    Array, ArrayRef, AsArray, BooleanArray, Float64Array, Int64Array, RecordBatch, StringArray,
    TimestampMicrosecondArray,
};
use arrow::compute::{cast, concat_batches};
use arrow::datatypes::{DataType, Field, Float64Type, Int64Type, Schema, TimeUnit};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use parquet::arrow::ArrowWriter;
use parquet::basic::Compression;
use parquet::file::properties::WriterProperties;

use crate::error::Error;

pub type Day = i32;

/// Days since 1970-01-01 of an ISO `YYYY-MM-DD` date (proleptic Gregorian).
pub fn parse_day(s: &str) -> Day {
    let s = s.trim();
    assert!(
        s.len() == 10
            && s.as_bytes()[4] == b'-'
            && s.as_bytes()[7] == b'-'
            && s.bytes()
                .enumerate()
                .all(|(i, b)| i == 4 || i == 7 || b.is_ascii_digit()),
        "date must be YYYY-MM-DD: {s}"
    );
    let p: Vec<i64> = s.trim().split('-').map(|x| x.parse().unwrap()).collect();
    assert_eq!(p.len(), 3, "date must be YYYY-MM-DD: {s}");
    assert!((1..=9999).contains(&p[0]), "invalid year: {s}");
    assert!((1..=12).contains(&p[1]), "invalid month: {s}");
    let leap = p[0] % 4 == 0 && (p[0] % 100 != 0 || p[0] % 400 == 0);
    let days = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    assert!(
        (1..=days[p[1] as usize - 1]).contains(&p[2]),
        "invalid day: {s}"
    );
    let (y, m, d) = (if p[1] <= 2 { p[0] - 1 } else { p[0] }, p[1], p[2]);
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let doy = (153 * ((m + 9) % 12) + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    (era * 146_097 + doe - 719_468) as Day
}

/// `(year, month, day)` of a day number.
pub fn civil(day: Day) -> (i32, u32, u32) {
    let z = day as i64 + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    ((yoe + era * 400 + i64::from(m <= 2)) as i32, m, d)
}

/// `YYYY-MM-DD`.
pub fn iso(day: Day) -> String {
    let (y, m, d) = civil(day);
    format!("{y:04}-{m:02}-{d:02}")
}
const US_PER_DAY: i64 = 86_400_000_000;

/// One parquet file held whole in memory.
pub struct Frame {
    batch: RecordBatch,
}

impl Frame {
    pub fn read(path: &Path) -> Frame {
        Frame::try_read(path).unwrap_or_else(|e| panic!("{e}"))
    }

    /// `read`, with the file named in every error.
    pub fn try_read(path: &Path) -> Result<Frame, Error> {
        let at = |e: &dyn std::fmt::Display| Error::at(path.display(), e);
        let file = File::open(path).map_err(|e| at(&e))?;
        let builder = ParquetRecordBatchReaderBuilder::try_new(file).map_err(|e| at(&e))?;
        let schema = builder.schema().clone();
        let reader = builder.build().map_err(|e| at(&e))?;
        let batches = reader
            .collect::<Result<Vec<RecordBatch>, _>>()
            .map_err(|e| at(&e))?;
        let batch = concat_batches(&schema, &batches).map_err(|e| at(&e))?;
        Ok(Frame::from_batch(batch))
    }

    /// An error naming `file` and every column of `cols` the frame lacks.
    pub fn need(&self, file: &str, cols: &[&str]) -> Result<(), Error> {
        let lacking: Vec<&str> = cols.iter().copied().filter(|c| !self.has(c)).collect();
        if lacking.is_empty() {
            Ok(())
        } else {
            Err(Error::at(
                file,
                format!(
                    "missing column {} (has {})",
                    lacking.join(", "),
                    self.names().join(", ")
                ),
            ))
        }
    }

    pub fn len(&self) -> usize {
        self.batch.num_rows()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub fn has(&self, name: &str) -> bool {
        self.batch.schema().index_of(name).is_ok()
    }

    fn col(&self, name: &str, to: &DataType) -> ArrayRef {
        let c = self
            .batch
            .column_by_name(name)
            .unwrap_or_else(|| panic!("no column {name}"));
        cast(c, to).unwrap()
    }

    pub fn str(&self, name: &str) -> Vec<String> {
        let c = self.col(name, &DataType::Utf8);
        let c = c.as_string::<i32>();
        (0..c.len())
            .map(|i| {
                if c.is_null(i) {
                    String::new()
                } else {
                    c.value(i).to_owned()
                }
            })
            .collect()
    }

    pub fn f64(&self, name: &str) -> Vec<f64> {
        let c = self.col(name, &DataType::Float64);
        let c = c.as_primitive::<Float64Type>();
        (0..c.len())
            .map(|i| if c.is_null(i) { f64::NAN } else { c.value(i) })
            .collect()
    }

    pub fn i64(&self, name: &str) -> Vec<i64> {
        self.opt_i64(name)
            .into_iter()
            .map(|x| x.unwrap_or_else(|| panic!("null in required integer column {name}")))
            .collect()
    }

    /// Nullable integers retain missingness; callers choose any domain default explicitly.
    pub fn opt_i64(&self, name: &str) -> Vec<Option<i64>> {
        let c = self.col(name, &DataType::Int64);
        let c = c.as_primitive::<Int64Type>();
        (0..c.len())
            .map(|i| (!c.is_null(i)).then(|| c.value(i)))
            .collect()
    }

    /// Required booleans; missing is not evidence of false.
    pub fn bool(&self, name: &str) -> Vec<bool> {
        let c = self.col(name, &DataType::Boolean);
        let c = c.as_boolean();
        assert_eq!(c.null_count(), 0, "null in required boolean column {name}");
        (0..c.len()).map(|i| c.value(i)).collect()
    }

    pub fn batch(&self) -> &RecordBatch {
        &self.batch
    }

    pub fn from_batch(batch: RecordBatch) -> Frame {
        let mut names = std::collections::HashSet::new();
        for f in batch.schema().fields() {
            assert!(
                names.insert(f.name().clone()),
                "duplicate column {}",
                f.name()
            );
        }
        Frame { batch }
    }

    pub fn names(&self) -> Vec<String> {
        self.batch
            .schema()
            .fields()
            .iter()
            .map(|f| f.name().clone())
            .collect()
    }

    /// Row `i` of the result is row `idx[i]` of `self`, all null where `None`.
    pub fn take(&self, idx: &[Option<usize>]) -> Frame {
        let ix: arrow::array::UInt64Array = idx.iter().map(|i| i.map(|i| i as u64)).collect();
        let columns = self
            .batch
            .columns()
            .iter()
            .map(|c| arrow::compute::take(c, &ix, None).unwrap())
            .collect();
        Frame {
            batch: RecordBatch::try_new(self.batch.schema(), columns).unwrap(),
        }
    }

    /// Append disjoint columns with equal row counts. A collision is a schema error.
    pub fn hstack(&self, others: &[&Frame]) -> Frame {
        let mut t = Table::default();
        for f in std::iter::once(self).chain(others.iter().copied()) {
            assert_eq!(self.len(), f.len(), "hstack row count mismatch");
            for (fi, c) in f.batch.schema().fields().iter().zip(f.batch.columns()) {
                t = t.push(fi.name(), c.clone());
            }
        }
        t.frame()
    }

    /// Keeps the named columns, in that order.
    pub fn select(&self, names: &[&str]) -> Frame {
        let mut t = Table::default();
        for n in names {
            t = t.push(
                n,
                self.batch
                    .column_by_name(n)
                    .unwrap_or_else(|| panic!("no column {n}"))
                    .clone(),
            );
        }
        t.frame()
    }

    pub fn write(&self, path: &Path) {
        let mut t = Table::default();
        for (fi, c) in self
            .batch
            .schema()
            .fields()
            .iter()
            .zip(self.batch.columns())
        {
            t = t.push(fi.name(), c.clone());
        }
        t.write(path)
    }

    pub fn day(&self, name: &str) -> Vec<Option<Day>> {
        let c = self.col(name, &DataType::Timestamp(TimeUnit::Microsecond, None));
        let c = c.as_primitive::<arrow::datatypes::TimestampMicrosecondType>();
        (0..c.len())
            .map(|i| (!c.is_null(i)).then(|| c.value(i).div_euclid(US_PER_DAY) as Day))
            .collect()
    }
}

/// A table under construction, written once.
#[derive(Clone, Default)]
pub struct Table {
    fields: Vec<Field>,
    columns: Vec<ArrayRef>,
}

impl Table {
    fn push(mut self, name: &str, a: ArrayRef) -> Table {
        assert!(
            !self.fields.iter().any(|f| f.name() == name),
            "duplicate column {name}"
        );
        self.fields
            .push(Field::new(name, a.data_type().clone(), true));
        self.columns.push(a);
        self
    }

    pub fn str<S: AsRef<str>>(self, name: &str, v: &[S]) -> Table {
        self.push(
            name,
            Arc::new(v.iter().map(|s| Some(s.as_ref())).collect::<StringArray>()),
        )
    }

    /// Strings with empty written as null.
    pub fn opt_str<S: AsRef<str>>(self, name: &str, v: &[S]) -> Table {
        let a: StringArray = v
            .iter()
            .map(|s| Some(s.as_ref()).filter(|s| !s.is_empty()))
            .collect();
        self.push(name, Arc::new(a))
    }

    /// Floats with NaN written as null.
    pub fn f64(self, name: &str, v: &[f64]) -> Table {
        self.push(
            name,
            Arc::new(
                v.iter()
                    .map(|x| (!x.is_nan()).then_some(*x))
                    .collect::<Float64Array>(),
            ),
        )
    }

    pub fn i64(self, name: &str, v: &[i64]) -> Table {
        self.push(name, Arc::new(Int64Array::from(v.to_vec())))
    }

    /// Integers with `None` written as null.
    pub fn opt_i64(self, name: &str, v: &[Option<i64>]) -> Table {
        self.push(name, Arc::new(v.iter().copied().collect::<Int64Array>()))
    }

    pub fn bool(self, name: &str, v: &[bool]) -> Table {
        self.push(name, Arc::new(BooleanArray::from(v.to_vec())))
    }

    pub fn day(self, name: &str, v: &[Option<Day>]) -> Table {
        let a: TimestampMicrosecondArray =
            v.iter().map(|d| d.map(|d| d as i64 * US_PER_DAY)).collect();
        self.push(name, Arc::new(a))
    }

    pub fn frame(self) -> Frame {
        let schema = Arc::new(Schema::new(self.fields));
        Frame {
            batch: RecordBatch::try_new(schema, self.columns).unwrap(),
        }
    }

    pub fn write(self, path: &Path) {
        let schema = Arc::new(Schema::new(self.fields));
        let batch = RecordBatch::try_new(schema.clone(), self.columns).unwrap();
        let props = WriterProperties::builder()
            .set_compression(Compression::SNAPPY)
            .build();
        let file = File::create(path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
        let mut w = ArrowWriter::try_new(file, schema, Some(props)).unwrap();
        w.write(&batch).unwrap();
        w.close().unwrap();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_missing_column_is_named_with_its_file() {
        let t = Table::default()
            .f64("mu", &[1.0])
            .str("fighter", &["A"])
            .frame();
        assert_eq!(t.need("ratings.parquet", &["mu", "fighter"]), Ok(()));
        let e = t
            .need("ratings.parquet", &["mu", "phi", "sigma"])
            .unwrap_err();
        assert_eq!(
            e.0,
            "ratings.parquet: missing column phi, sigma (has mu, fighter)"
        );
        let e = Frame::try_read(Path::new("no/such.parquet")).err().unwrap();
        assert!(e.0.starts_with("no/such.parquet: "), "{e}");
    }

    #[test]
    fn gregorian_dates_reject_normalization() {
        for s in [
            "2026-02-30",
            "2026-13-01",
            "1900-02-29",
            "2026-04-31",
            "2026-01-01-02",
            "2026-00-10",
        ] {
            assert!(std::panic::catch_unwind(|| parse_day(s)).is_err(), "{s}");
        }
        for s in ["2000-02-29", "2024-02-29", "1970-01-01", "2026-12-31"] {
            assert_eq!(iso(parse_day(s)), s);
        }
    }

    #[test]
    fn required_columns_do_not_impute_missing_values() {
        let f = Table::default().opt_i64("count", &[None, Some(0)]).frame();
        assert_eq!(f.opt_i64("count"), [None, Some(0)]);
        assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| f.i64("count"))).is_err());
        let f = Frame::from_batch(
            RecordBatch::try_new(
                Arc::new(Schema::new(vec![Field::new(
                    "flag",
                    DataType::Boolean,
                    true,
                )])),
                vec![Arc::new(BooleanArray::from(vec![None, Some(false)]))],
            )
            .unwrap(),
        );
        assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| f.bool("flag"))).is_err());
    }

    #[test]
    #[should_panic(expected = "duplicate column score")]
    fn stages_cannot_silently_shadow_columns() {
        Table::default()
            .i64("score", &[1])
            .frame()
            .hstack(&[&Table::default().i64("score", &[99]).frame()]);
    }
}
