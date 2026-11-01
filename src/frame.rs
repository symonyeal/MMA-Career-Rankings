//! Parquet shell: columns in as plain vectors, columns out as a table.
//!
//! Dates are days since 1970-01-01 (`Day`); missing numbers are NaN, missing
//! strings are empty, missing days are `None`. Pandas wrote every snapshot
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

pub type Day = i32;

/// Days since 1970-01-01 of an ISO `YYYY-MM-DD` date (proleptic Gregorian).
pub fn parse_day(s: &str) -> Day {
    let p: Vec<i64> = s.trim().split('-').map(|x| x.parse().unwrap()).collect();
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
        let file = File::open(path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
        let builder = ParquetRecordBatchReaderBuilder::try_new(file).unwrap();
        let schema = builder.schema().clone();
        let reader = builder.build().unwrap();
        let batches: Vec<RecordBatch> = reader.map(Result::unwrap).collect();
        Frame { batch: concat_batches(&schema, &batches).unwrap() }
    }

    pub fn len(&self) -> usize {
        self.batch.num_rows()
    }

    pub fn has(&self, name: &str) -> bool {
        self.batch.schema().index_of(name).is_ok()
    }

    fn col(&self, name: &str, to: &DataType) -> ArrayRef {
        let c = self.batch.column_by_name(name).unwrap_or_else(|| panic!("no column {name}"));
        cast(c, to).unwrap()
    }

    pub fn str(&self, name: &str) -> Vec<String> {
        let c = self.col(name, &DataType::Utf8);
        let c = c.as_string::<i32>();
        (0..c.len()).map(|i| if c.is_null(i) { String::new() } else { c.value(i).to_owned() }).collect()
    }

    pub fn f64(&self, name: &str) -> Vec<f64> {
        let c = self.col(name, &DataType::Float64);
        let c = c.as_primitive::<Float64Type>();
        (0..c.len()).map(|i| if c.is_null(i) { f64::NAN } else { c.value(i) }).collect()
    }

    pub fn i64(&self, name: &str) -> Vec<i64> {
        let c = self.col(name, &DataType::Int64);
        let c = c.as_primitive::<Int64Type>();
        (0..c.len()).map(|i| if c.is_null(i) { 0 } else { c.value(i) }).collect()
    }

    /// Booleans; a missing value reads false, as pandas' `fillna(False)` did.
    pub fn bool(&self, name: &str) -> Vec<bool> {
        let c = self.col(name, &DataType::Boolean);
        let c = c.as_boolean();
        (0..c.len()).map(|i| !c.is_null(i) && c.value(i)).collect()
    }

    pub fn names(&self) -> Vec<String> {
        self.batch.schema().fields().iter().map(|f| f.name().clone()).collect()
    }

    /// Row `i` of the result is row `idx[i]` of `self`, all null where `None`.
    pub fn take(&self, idx: &[Option<usize>]) -> Frame {
        let ix: arrow::array::UInt64Array = idx.iter().map(|i| i.map(|i| i as u64)).collect();
        let columns = self.batch.columns().iter().map(|c| arrow::compute::take(c, &ix, None).unwrap()).collect();
        Frame { batch: RecordBatch::try_new(self.batch.schema(), columns).unwrap() }
    }

    /// Columns of `others` appended to `self` (equal row counts; later duplicates are dropped).
    pub fn hstack(&self, others: &[&Frame]) -> Frame {
        let mut t = Table::default();
        for f in std::iter::once(self).chain(others.iter().copied()) {
            for (fi, c) in f.batch.schema().fields().iter().zip(f.batch.columns()) {
                if !t.fields.iter().any(|x| x.name() == fi.name()) {
                    t = t.push(fi.name(), c.clone());
                }
            }
        }
        t.frame()
    }

    /// Keeps the named columns, in that order.
    pub fn select(&self, names: &[&str]) -> Frame {
        let mut t = Table::default();
        for n in names {
            t = t.push(n, self.batch.column_by_name(n).unwrap_or_else(|| panic!("no column {n}")).clone());
        }
        t.frame()
    }

    pub fn write(&self, path: &Path) {
        let mut t = Table::default();
        for (fi, c) in self.batch.schema().fields().iter().zip(self.batch.columns()) {
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
#[derive(Default)]
pub struct Table {
    fields: Vec<Field>,
    columns: Vec<ArrayRef>,
}

impl Table {
    fn push(mut self, name: &str, a: ArrayRef) -> Table {
        self.fields.push(Field::new(name, a.data_type().clone(), true));
        self.columns.push(a);
        self
    }

    pub fn str<S: AsRef<str>>(self, name: &str, v: &[S]) -> Table {
        self.push(name, Arc::new(v.iter().map(|s| Some(s.as_ref())).collect::<StringArray>()))
    }

    /// Strings with empty written as null.
    pub fn opt_str<S: AsRef<str>>(self, name: &str, v: &[S]) -> Table {
        let a: StringArray = v.iter().map(|s| Some(s.as_ref()).filter(|s| !s.is_empty())).collect();
        self.push(name, Arc::new(a))
    }

    /// Floats with NaN written as null.
    pub fn f64(self, name: &str, v: &[f64]) -> Table {
        self.push(name, Arc::new(v.iter().map(|x| (!x.is_nan()).then_some(*x)).collect::<Float64Array>()))
    }

    pub fn i64(self, name: &str, v: &[i64]) -> Table {
        self.push(name, Arc::new(Int64Array::from(v.to_vec())))
    }

    pub fn bool(self, name: &str, v: &[bool]) -> Table {
        self.push(name, Arc::new(BooleanArray::from(v.to_vec())))
    }

    pub fn day(self, name: &str, v: &[Option<Day>]) -> Table {
        let a: TimestampMicrosecondArray = v.iter().map(|d| d.map(|d| d as i64 * US_PER_DAY)).collect();
        self.push(name, Arc::new(a))
    }

    pub fn frame(self) -> Frame {
        let schema = Arc::new(Schema::new(self.fields));
        Frame { batch: RecordBatch::try_new(schema, self.columns).unwrap() }
    }

    pub fn write(self, path: &Path) {
        let schema = Arc::new(Schema::new(self.fields));
        let batch = RecordBatch::try_new(schema.clone(), self.columns).unwrap();
        let props = WriterProperties::builder().set_compression(Compression::SNAPPY).build();
        let file = File::create(path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
        let mut w = ArrowWriter::try_new(file, schema, Some(props)).unwrap();
        w.write(&batch).unwrap();
        w.close().unwrap();
    }
}
