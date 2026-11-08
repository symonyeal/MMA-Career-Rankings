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
pub fn parse_day(s: &str) -> Result<Day, Error> {
    let bad = || Error::at(s, "date must be YYYY-MM-DD");
    let t = s.trim();
    let b = t.as_bytes();
    if b.len() != 10
        || b[4] != b'-'
        || b[7] != b'-'
        || !b
            .iter()
            .enumerate()
            .all(|(i, c)| i == 4 || i == 7 || c.is_ascii_digit())
    {
        return Err(bad());
    }
    let n = |r: std::ops::Range<usize>| t[r].parse::<i64>().map_err(|_| bad());
    let (y0, m, d) = (n(0..4)?, n(5..7)?, n(8..10)?);
    let leap = y0 % 4 == 0 && (y0 % 100 != 0 || y0 % 400 == 0);
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
    if !(1..=9999).contains(&y0)
        || !(1..=12).contains(&m)
        || !(1..=days[m as usize - 1]).contains(&d)
    {
        return Err(Error::at(s, "not a calendar date"));
    }
    let y = if m <= 2 { y0 - 1 } else { y0 };
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let doy = (153 * ((m + 9) % 12) + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    Ok((era * 146_097 + doe - 719_468) as Day)
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

/// A text file with LF line ends.
pub fn read_text(path: &Path) -> Result<String, Error> {
    let text = std::fs::read_to_string(path).map_err(|e| Error::at(path.display(), e))?;
    Ok(text.replace("\r\n", "\n"))
}

pub fn write_text(path: &Path, text: &str) -> Result<(), Error> {
    std::fs::write(path, text).map_err(|e| Error::at(path.display(), e))
}

/// The CSV at `path` as rows of the named columns, in that order; errors name the file and row.
pub fn csv_rows(path: &Path, cols: &[&str]) -> Result<Vec<Vec<String>>, Error> {
    let at = |e: &dyn std::fmt::Display| Error::at(path.display(), e);
    let mut rd = csv::Reader::from_path(path).map_err(|e| at(&e))?;
    let h = rd.headers().map_err(|e| at(&e))?.clone();
    let ix = cols
        .iter()
        .map(|c| {
            h.iter()
                .position(|x| x == *c)
                .ok_or_else(|| at(&format!("missing column {c}")))
        })
        .collect::<Result<Vec<_>, _>>()?;
    rd.records()
        .enumerate()
        .map(|(i, r)| {
            let r = r.map_err(|e| at(&format!("row {}: {e}", i + 2)))?;
            Ok(ix.iter().map(|&j| r[j].to_string()).collect())
        })
        .collect()
}

/// One parquet file held whole in memory.
pub struct Frame {
    batch: RecordBatch,
    /// The file it was read from, empty for a table built in memory; named in column errors.
    file: String,
}

impl Frame {
    /// The file at `path`, which must hold every column of `cols`; each error names the file.
    pub fn read(path: &Path, cols: &[&str]) -> Result<Frame, Error> {
        let at = |e: &dyn std::fmt::Display| Error::at(path.display(), e);
        let file = File::open(path).map_err(|e| at(&e))?;
        let builder = ParquetRecordBatchReaderBuilder::try_new(file).map_err(|e| at(&e))?;
        let schema = builder.schema().clone();
        let reader = builder.build().map_err(|e| at(&e))?;
        let batches = reader
            .collect::<Result<Vec<RecordBatch>, _>>()
            .map_err(|e| at(&e))?;
        let batch = concat_batches(&schema, &batches).map_err(|e| at(&e))?;
        let mut f = Frame::from_batch(batch)?;
        f.file = path.display().to_string();
        f.need(&f.file, cols)?;
        Ok(f)
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

    /// `file: column name: message`, or `column name: message` for a table built in memory.
    fn at(&self, name: &str, message: impl std::fmt::Display) -> Error {
        let context = if self.file.is_empty() {
            format!("column {name}")
        } else {
            format!("{} column {name}", self.file)
        };
        Error::at(context, message)
    }

    fn col(&self, name: &str, to: &DataType) -> Result<ArrayRef, Error> {
        let c = self
            .batch
            .column_by_name(name)
            .ok_or_else(|| self.at(name, "no such column"))?;
        cast(c, to).map_err(|e| self.at(name, e))
    }

    pub fn str(&self, name: &str) -> Result<Vec<String>, Error> {
        let c = self.col(name, &DataType::Utf8)?;
        let c = c.as_string::<i32>();
        Ok((0..c.len())
            .map(|i| {
                if c.is_null(i) {
                    String::new()
                } else {
                    c.value(i).to_owned()
                }
            })
            .collect())
    }

    pub fn f64(&self, name: &str) -> Result<Vec<f64>, Error> {
        let c = self.col(name, &DataType::Float64)?;
        let c = c.as_primitive::<Float64Type>();
        Ok((0..c.len())
            .map(|i| if c.is_null(i) { f64::NAN } else { c.value(i) })
            .collect())
    }

    /// Floats with NaN replaced by `fill`.
    pub fn f64_or(&self, name: &str, fill: f64) -> Result<Vec<f64>, Error> {
        Ok(self
            .f64(name)?
            .into_iter()
            .map(|x| if x.is_nan() { fill } else { x })
            .collect())
    }

    /// Required integers: a null is an error naming the column and row.
    pub fn i64(&self, name: &str) -> Result<Vec<i64>, Error> {
        self.opt_i64(name)?
            .into_iter()
            .enumerate()
            .map(|(i, x)| {
                x.ok_or_else(|| self.at(name, format!("null in required integer, row {i}")))
            })
            .collect()
    }

    /// Nullable integers retain missingness; callers choose any domain default explicitly.
    pub fn opt_i64(&self, name: &str) -> Result<Vec<Option<i64>>, Error> {
        let c = self.col(name, &DataType::Int64)?;
        let c = c.as_primitive::<Int64Type>();
        Ok((0..c.len())
            .map(|i| (!c.is_null(i)).then(|| c.value(i)))
            .collect())
    }

    /// Required booleans; missing is not evidence of false.
    pub fn bool(&self, name: &str) -> Result<Vec<bool>, Error> {
        let c = self.col(name, &DataType::Boolean)?;
        let c = c.as_boolean();
        if let Some(i) = (0..c.len()).find(|&i| c.is_null(i)) {
            return Err(self.at(name, format!("null in required boolean, row {i}")));
        }
        Ok((0..c.len()).map(|i| c.value(i)).collect())
    }

    pub fn batch(&self) -> &RecordBatch {
        &self.batch
    }

    pub fn from_batch(batch: RecordBatch) -> Result<Frame, Error> {
        let mut names = std::collections::HashSet::new();
        for f in batch.schema().fields() {
            if !names.insert(f.name().clone()) {
                return Err(Error::at("table", format!("duplicate column {}", f.name())));
            }
        }
        Ok(Frame {
            batch,
            file: String::new(),
        })
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
    pub fn take(&self, idx: &[Option<usize>]) -> Result<Frame, Error> {
        let ix: arrow::array::UInt64Array = idx.iter().map(|i| i.map(|i| i as u64)).collect();
        let columns = self
            .batch
            .columns()
            .iter()
            .map(|c| arrow::compute::take(c, &ix, None))
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| Error::at("take", e))?;
        let batch =
            RecordBatch::try_new(self.batch.schema(), columns).map_err(|e| Error::at("take", e))?;
        Ok(Frame {
            batch,
            file: String::new(),
        })
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
    pub fn select(&self, names: &[&str]) -> Result<Frame, Error> {
        let mut t = Table::default();
        for n in names {
            let c = self
                .batch
                .column_by_name(n)
                .ok_or_else(|| self.at(n, "no such column"))?;
            t = t.push(n, c.clone());
        }
        Ok(t.frame())
    }

    pub fn write(&self, path: &Path) -> Result<(), Error> {
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

    /// Required dates: a null is an error naming the column and row.
    pub fn days(&self, name: &str) -> Result<Vec<Day>, Error> {
        self.day(name)?
            .into_iter()
            .enumerate()
            .map(|(i, d)| d.ok_or_else(|| self.at(name, format!("null in required date, row {i}"))))
            .collect()
    }

    pub fn day(&self, name: &str) -> Result<Vec<Option<Day>>, Error> {
        let c = self.col(name, &DataType::Timestamp(TimeUnit::Microsecond, None))?;
        let c = c.as_primitive::<arrow::datatypes::TimestampMicrosecondType>();
        Ok((0..c.len())
            .map(|i| (!c.is_null(i)).then(|| c.value(i).div_euclid(US_PER_DAY) as Day))
            .collect())
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
            batch: RecordBatch::try_new(schema, self.columns).expect("columns of equal length"),
            file: String::new(),
        }
    }

    pub fn write(self, path: &Path) -> Result<(), Error> {
        let at = |e: &dyn std::fmt::Display| Error::at(path.display(), e);
        let schema = Arc::new(Schema::new(self.fields));
        let batch = RecordBatch::try_new(schema.clone(), self.columns).map_err(|e| at(&e))?;
        let props = WriterProperties::builder()
            .set_compression(Compression::SNAPPY)
            .build();
        let file = File::create(path).map_err(|e| at(&e))?;
        let mut w = ArrowWriter::try_new(file, schema, Some(props)).map_err(|e| at(&e))?;
        w.write(&batch).map_err(|e| at(&e))?;
        w.close().map_err(|e| at(&e))?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(name: &str) -> std::path::PathBuf {
        let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("target/frame-tests");
        std::fs::create_dir_all(&dir).unwrap();
        dir.join(name)
    }

    #[test]
    fn a_missing_column_is_named_with_its_file() {
        let path = scratch("ratings.parquet");
        Table::default()
            .f64("mu", &[1.0])
            .str("fighter", &["A"])
            .write(&path)
            .unwrap();
        assert!(Frame::read(&path, &["mu", "fighter"]).is_ok());
        let e = Frame::read(&path, &["mu", "phi", "sigma"]).err().unwrap();
        assert_eq!(
            e.0,
            format!(
                "{}: missing column phi, sigma (has mu, fighter)",
                path.display()
            )
        );
        let e = Frame::read(Path::new("no/such.parquet"), &[])
            .err()
            .unwrap();
        assert!(e.0.starts_with("no/such.parquet: "), "{e}");
    }

    #[test]
    fn an_accessor_on_a_missing_column_names_the_file_and_column() {
        let path = scratch("accessor.parquet");
        Table::default().f64("mu", &[1.0]).write(&path).unwrap();
        let f = Frame::read(&path, &["mu"]).unwrap();
        let e = f.f64("phi").unwrap_err();
        assert_eq!(
            e.0,
            format!("{} column phi: no such column", path.display())
        );
        assert!(f.select(&["phi"]).is_err());
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
            assert!(parse_day(s).is_err(), "{s}");
        }
        for s in ["2000-02-29", "2024-02-29", "1970-01-01", "2026-12-31"] {
            assert_eq!(iso(parse_day(s).unwrap()), s);
        }
    }

    #[test]
    fn required_columns_do_not_impute_missing_values() {
        let f = Table::default().opt_i64("count", &[None, Some(0)]).frame();
        assert_eq!(f.opt_i64("count").unwrap(), [None, Some(0)]);
        let e = f.i64("count").unwrap_err();
        assert_eq!(e.0, "column count: null in required integer, row 0");
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
        )
        .unwrap();
        let e = f.bool("flag").unwrap_err();
        assert_eq!(e.0, "column flag: null in required boolean, row 0");
    }

    #[test]
    fn a_csv_missing_column_is_named() {
        let path = scratch("rules.csv");
        std::fs::write(&path, "a,b\n1,2\n").unwrap();
        assert_eq!(csv_rows(&path, &["b", "a"]).unwrap(), [["2", "1"]]);
        let e = csv_rows(&path, &["a", "c"]).unwrap_err();
        assert_eq!(e.0, format!("{}: missing column c", path.display()));
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
