//! How firmly a fighter is tied to the rated core of the bout graph.
//!
//! The measure is the number of vertex-disjoint paths from the fighter to an
//! anchor (a core fighter with at least three core bouts), by Menger's theorem
//! the maximum flow when every intermediary has capacity one. Counting stops at
//! three, the floor at which a single mis-rated intermediary cannot decide a
//! placement; a fighter in the core, or with three paths, is rankable.

use std::collections::{HashMap, HashSet, VecDeque};

/// `DEFAULT_MIN_DISJOINT_PATHS`.
pub const MIN_PATHS: usize = 3;
/// `DEFAULT_MIN_BRIDGE_BOUTS`.
pub const MIN_BRIDGE_BOUTS: usize = 3;

/// Split-vertex flow network: fighter v has in-node 2v and out-node 2v+1, the sink is last.
pub struct Graph {
    id: HashMap<String, usize>,
    anchor: Vec<bool>,
    head: Vec<usize>,
    cap0: Vec<u8>,
    to: Vec<usize>,
    next: Vec<usize>,
    sink: usize,
}

const NIL: usize = usize::MAX;

impl Graph {
    /// `bouts` are (fighter_a, fighter_b) pairs; `counts` the core bout count of each core fighter.
    pub fn new<'a>(
        bouts: impl Iterator<Item = (&'a str, &'a str)>,
        counts: &HashMap<String, usize>,
    ) -> Graph {
        let mut id: HashMap<String, usize> = HashMap::new();
        let mut adj: Vec<HashSet<usize>> = Vec::new();
        let mut node = |n: &str, adj: &mut Vec<HashSet<usize>>| {
            *id.entry(n.to_string()).or_insert_with(|| {
                adj.push(HashSet::new());
                adj.len() - 1
            })
        };
        for (x, y) in bouts {
            if !x.is_empty() && !y.is_empty() && x != y {
                let (i, j) = (node(x, &mut adj), node(y, &mut adj));
                adj[i].insert(j);
                adj[j].insert(i);
            }
        }
        let n = adj.len();
        let mut anchor = vec![false; n];
        for (name, &v) in &id {
            anchor[v] = counts.get(name).is_some_and(|&c| c >= MIN_BRIDGE_BOUTS);
        }
        let sink = 2 * n;
        let mut g = Graph {
            id,
            anchor,
            head: vec![NIL; 2 * n + 1],
            cap0: vec![],
            to: vec![],
            next: vec![],
            sink,
        };
        for v in 0..n {
            g.edge(2 * v, 2 * v + 1);
            if g.anchor[v] {
                g.edge(2 * v + 1, sink);
            }
            for &w in &adj[v] {
                g.edge(2 * v + 1, 2 * w);
            }
        }
        g
    }

    fn edge(&mut self, u: usize, v: usize) {
        for (a, b, c) in [(u, v, 1), (v, u, 0)] {
            self.to.push(b);
            self.cap0.push(c);
            self.next.push(self.head[a]);
            self.head[a] = self.to.len() - 1;
        }
    }

    /// Vertex-disjoint paths from `source` to the anchors, at most `MIN_PATHS`; `None` off the graph.
    pub fn paths(&self, source: &str) -> Option<usize> {
        let s = *self.id.get(source)?;
        if self.anchor[s] {
            return Some(MIN_PATHS);
        }
        let mut cap = self.cap0.clone();
        let mut flow = 0;
        while flow < MIN_PATHS {
            let mut via = vec![NIL; self.head.len()];
            let start = 2 * s + 1;
            via[start] = usize::MAX - 1;
            let mut q = VecDeque::from([start]);
            while let Some(u) = q.pop_front() {
                if u == self.sink {
                    break;
                }
                let mut e = self.head[u];
                while e != NIL {
                    let v = self.to[e];
                    if cap[e] > 0 && via[v] == NIL {
                        via[v] = e;
                        q.push_back(v);
                    }
                    e = self.next[e];
                }
            }
            if via[self.sink] == NIL {
                break;
            }
            let mut v = self.sink;
            while v != start {
                let e = via[v];
                cap[e] -= 1;
                cap[e ^ 1] += 1;
                v = self.to[e ^ 1];
            }
            flow += 1;
        }
        Some(flow)
    }
}
