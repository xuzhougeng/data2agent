package portal

import (
	"context"
	"database/sql"
	"fmt"
	"math"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	_ "github.com/marcboeker/go-duckdb/v2"
)

// Store is a read-only DuckDB over the package's parquet files, exposing the contract views.
// ponytail: one in-memory DuckDB per process; a Postgres-backed Store is the XL tier, not needed yet.
type Store struct {
	DB      *sql.DB
	M       *Manifest
	Pkg     string
	MaxRows int
	Timeout time.Duration

	views map[string]View
	mu    sync.Mutex
	cols  map[string]map[string]bool // view -> actual parquet columns
}

func Open(pkg string) (*Store, error) {
	abs, err := filepath.Abs(pkg)
	if err != nil {
		return nil, err
	}
	m, err := LoadManifest(abs)
	if err != nil {
		return nil, err
	}
	db, err := sql.Open("duckdb", "")
	if err != nil {
		return nil, err
	}
	s := &Store{DB: db, M: m, Pkg: abs, MaxRows: 1000, Timeout: 30 * time.Second, views: map[string]View{}, cols: map[string]map[string]bool{}}
	for _, v := range m.Views() {
		s.views[v.Name] = v
		var srcs []string
		for _, p := range v.Paths {
			srcs = append(srcs, "'"+strings.ReplaceAll(filepath.Join(abs, filepath.FromSlash(p)), "'", "''")+"'")
		}
		src := srcs[0]
		if len(srcs) > 1 {
			src = "[" + strings.Join(srcs, ",") + "]"
		}
		if _, err := db.Exec(fmt.Sprintf(`create view %s as select * from read_parquet(%s)`, Ident(v.Name), src)); err != nil {
			return nil, fmt.Errorf("view %s: %w", v.Name, err)
		}
	}
	return s, nil
}

var identRe = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_ .+-]*$`)

// Ident quotes an identifier for SQL.
func Ident(s string) string {
	return `"` + strings.ReplaceAll(s, `"`, `""`) + `"`
}

func (s *Store) HasView(name string) bool { _, ok := s.views[name]; return ok }

// HasColumn reports whether view has a column named col (from parquet metadata, cached).
func (s *Store) HasColumn(ctx context.Context, view, col string) bool {
	if !identRe.MatchString(col) || !s.HasView(view) {
		return false
	}
	s.mu.Lock()
	cols, ok := s.cols[view]
	s.mu.Unlock()
	if !ok {
		cols = map[string]bool{}
		res, err := s.Query(ctx, "describe select * from "+Ident(view))
		if err == nil {
			for _, r := range res.Rows {
				if n, ok := r["column_name"].(string); ok {
					cols[n] = true
				}
			}
		}
		s.mu.Lock()
		s.cols[view] = cols
		s.mu.Unlock()
	}
	return cols[col]
}

// Result is the wire shape every list-like endpoint returns.
type Result struct {
	Columns []string         `json:"columns"`
	Rows    []map[string]any `json:"rows"`
}

// Query runs a statement and returns rows as JSON-friendly maps.
func (s *Store) Query(ctx context.Context, q string, args ...any) (*Result, error) {
	ctx, cancel := context.WithTimeout(ctx, s.Timeout)
	defer cancel()
	rows, err := s.DB.QueryContext(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	cols, err := rows.Columns()
	if err != nil {
		return nil, err
	}
	res := &Result{Columns: cols, Rows: []map[string]any{}}
	vals := make([]any, len(cols))
	ptrs := make([]any, len(cols))
	for i := range vals {
		ptrs[i] = &vals[i]
	}
	for rows.Next() {
		if err := rows.Scan(ptrs...); err != nil {
			return nil, err
		}
		row := make(map[string]any, len(cols))
		for i, c := range cols {
			row[c] = jsonValue(vals[i])
		}
		res.Rows = append(res.Rows, row)
	}
	return res, rows.Err()
}

func jsonValue(v any) any {
	switch x := v.(type) {
	case []byte:
		return string(x)
	case float32:
		if math.IsNaN(float64(x)) || math.IsInf(float64(x), 0) {
			return nil
		}
		return x
	case float64:
		if math.IsNaN(x) || math.IsInf(x, 0) {
			return nil
		}
		return x
	case time.Time:
		return x.Format(time.RFC3339)
	default:
		return v
	}
}

// Filters mirrors api.static.js: {"col": [values]} | {"col": {"min":x,"max":y}} | {"q": "text"}.
type Filters map[string]any

// Where builds a parameterised WHERE clause for view. textCols are searched by "q".
func (s *Store) Where(ctx context.Context, view string, f Filters, textCols []string) (string, []any, error) {
	var parts []string
	var args []any
	for col, v := range f {
		if col == "q" {
			t, _ := v.(string)
			if t == "" {
				continue
			}
			var ors []string
			for _, c := range textCols {
				if s.HasColumn(ctx, view, c) {
					ors = append(ors, "cast("+Ident(c)+" as varchar) ilike ?")
					args = append(args, "%"+t+"%")
				}
			}
			if len(ors) > 0 {
				parts = append(parts, "("+strings.Join(ors, " or ")+")")
			}
			continue
		}
		if !s.HasColumn(ctx, view, col) {
			return "", nil, fmt.Errorf("unknown column %q", col)
		}
		switch x := v.(type) {
		case []any:
			if len(x) == 0 {
				continue
			}
			ph := make([]string, len(x))
			for i, item := range x {
				ph[i] = "?"
				args = append(args, fmt.Sprint(item))
			}
			parts = append(parts, "cast("+Ident(col)+" as varchar) in ("+strings.Join(ph, ",")+")")
		case map[string]any:
			if mn, ok := x["min"].(float64); ok {
				parts = append(parts, Ident(col)+" >= ?")
				args = append(args, mn)
			}
			if mx, ok := x["max"].(float64); ok {
				parts = append(parts, Ident(col)+" <= ?")
				args = append(args, mx)
			}
		}
	}
	if len(parts) == 0 {
		return "", args, nil
	}
	return "where " + strings.Join(parts, " and "), args, nil
}

// Order mirrors {"col": name, "desc": bool}.
type Order struct {
	Col  string `json:"col"`
	Desc bool   `json:"desc"`
}

func (s *Store) OrderBy(ctx context.Context, view string, o *Order) (string, error) {
	if o == nil || o.Col == "" {
		return "", nil
	}
	if !s.HasColumn(ctx, view, o.Col) {
		return "", fmt.Errorf("unknown column %q", o.Col)
	}
	dir := "asc"
	if o.Desc {
		dir = "desc"
	}
	return "order by " + Ident(o.Col) + " " + dir + " nulls last", nil
}

var (
	readOnlyRe = regexp.MustCompile(`(?i)^\s*(select|with|describe|show|explain|pragma|summarize)\b`)
	selectRe   = regexp.MustCompile(`(?i)^\s*(select|with)\b`)
)

// SQL runs a user query read-only with a row cap; same rules as the browser console.
func (s *Store) SQL(ctx context.Context, q string, limit int) (*Result, error) {
	q = strings.TrimSpace(strings.TrimRight(strings.TrimSpace(q), ";"))
	if !readOnlyRe.MatchString(q) {
		return nil, fmt.Errorf("only read-only SELECT/WITH queries are allowed")
	}
	if strings.Contains(q, ";") {
		return nil, fmt.Errorf("one statement at a time")
	}
	if limit <= 0 || limit > s.MaxRows {
		limit = s.MaxRows
	}
	if !selectRe.MatchString(q) {
		return s.Query(ctx, q)
	}
	return s.Query(ctx, fmt.Sprintf("select * from (%s) limit %d", q, limit))
}
