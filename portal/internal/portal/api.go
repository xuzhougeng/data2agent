package portal

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
)

// Handler implements api-contract.json over a Store and serves the static site from the package dir.
func Handler(s *Store) http.Handler {
	mux := http.NewServeMux()
	a := &api{s: s}

	mux.HandleFunc("GET /api/manifest", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write(s.M.Raw)
	})
	mux.HandleFunc("GET /api/obs/count", a.obsCount)
	mux.HandleFunc("GET /api/obs/facets", a.obsFacets)
	mux.HandleFunc("GET /api/obs", a.obsList)
	mux.HandleFunc("GET /api/obs/{id}", a.obsGet)
	mux.HandleFunc("GET /api/features/search", a.featuresSearch)
	mux.HandleFunc("GET /api/features/where", a.featuresWhere)
	mux.HandleFunc("GET /api/features/{id}", a.featuresGet)
	mux.HandleFunc("GET /api/matrix/feature/{id}", a.matrixFeature)
	mux.HandleFunc("GET /api/figure/{id}", a.figure)
	mux.HandleFunc("GET /api/embedding/{name}", a.embedding)
	mux.HandleFunc("GET /api/agg/feature_group/{id}", a.aggFeatureGroup)
	mux.HandleFunc("GET /api/feature_results/{id}", a.resultsForFeature)
	mux.HandleFunc("GET /api/results/{name}/count", a.resultsCount)
	mux.HandleFunc("GET /api/results/{name}/facets", a.resultsFacets)
	mux.HandleFunc("GET /api/results/{name}/all", a.resultsAll)
	mux.HandleFunc("GET /api/results/{name}", a.resultsList)
	mux.HandleFunc("POST /api/sql", a.sql)
	mux.HandleFunc("/api/", func(w http.ResponseWriter, r *http.Request) { fail(w, 404, errors.New("unknown endpoint")) })

	fs := http.FileServer(http.Dir(s.Pkg))
	mux.Handle("/", noDirListing(fs))
	return mux
}

type api struct{ s *Store }

// ---- helpers

func fail(w http.ResponseWriter, code int, err error) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
}

func ok(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "public, max-age=60")
	json.NewEncoder(w).Encode(v)
}

func parseFilters(r *http.Request) (Filters, error) {
	f := Filters{}
	if raw := r.URL.Query().Get("filters"); raw != "" {
		if err := json.Unmarshal([]byte(raw), &f); err != nil {
			return nil, fmt.Errorf("filters: %w", err)
		}
	}
	return f, nil
}

func parseOrder(r *http.Request) (*Order, error) {
	raw := r.URL.Query().Get("order")
	if raw == "" {
		return nil, nil
	}
	var o Order
	if err := json.Unmarshal([]byte(raw), &o); err != nil {
		return nil, fmt.Errorf("order: %w", err)
	}
	return &o, nil
}

func intParam(r *http.Request, name string, def, max int) int {
	v, err := strconv.Atoi(r.URL.Query().Get(name))
	if err != nil || v < 0 {
		return def
	}
	if max > 0 && v > max {
		return max
	}
	return v
}

func (a *api) list(w http.ResponseWriter, r *http.Request, view string, textCols []string, defLimit, maxLimit int) {
	f, err := parseFilters(r)
	if err != nil {
		fail(w, 400, err)
		return
	}
	o, err := parseOrder(r)
	if err != nil {
		fail(w, 400, err)
		return
	}
	where, args, err := a.s.Where(r.Context(), view, f, textCols)
	if err != nil {
		fail(w, 400, err)
		return
	}
	order, err := a.s.OrderBy(r.Context(), view, o)
	if err != nil {
		fail(w, 400, err)
		return
	}
	limit, offset := intParam(r, "limit", defLimit, maxLimit), intParam(r, "offset", 0, 0)
	res, err := a.s.Query(r.Context(), fmt.Sprintf("select * from %s %s %s limit %d offset %d", Ident(view), where, order, limit, offset), args...)
	if err != nil {
		fail(w, 500, err)
		return
	}
	ok(w, res)
}

func (a *api) count(w http.ResponseWriter, r *http.Request, view string, textCols []string) {
	f, err := parseFilters(r)
	if err != nil {
		fail(w, 400, err)
		return
	}
	where, args, err := a.s.Where(r.Context(), view, f, textCols)
	if err != nil {
		fail(w, 400, err)
		return
	}
	res, err := a.s.Query(r.Context(), fmt.Sprintf("select count(*) as n from %s %s", Ident(view), where), args...)
	if err != nil {
		fail(w, 500, err)
		return
	}
	ok(w, res.Rows[0]["n"])
}

func (a *api) facets(w http.ResponseWriter, r *http.Request, view string, textCols []string) {
	f, err := parseFilters(r)
	if err != nil {
		fail(w, 400, err)
		return
	}
	out := map[string][]map[string]any{}
	for _, c := range strings.Split(r.URL.Query().Get("cols"), ",") {
		if c == "" {
			continue
		}
		if !a.s.HasColumn(r.Context(), view, c) {
			fail(w, 400, fmt.Errorf("unknown column %q", c))
			return
		}
		sub := Filters{}
		for k, v := range f {
			if k != c { // a facet's own selection does not restrict its counts
				sub[k] = v
			}
		}
		where, args, err := a.s.Where(r.Context(), view, sub, textCols)
		if err != nil {
			fail(w, 400, err)
			return
		}
		res, err := a.s.Query(r.Context(), fmt.Sprintf(`select cast(%s as varchar) as "value", count(*) as n from %s %s group by 1 order by n desc, 1 limit 60`, Ident(c), Ident(view), where), args...)
		if err != nil {
			fail(w, 500, err)
			return
		}
		out[c] = res.Rows
	}
	ok(w, out)
}

func (a *api) getOne(w http.ResponseWriter, r *http.Request, view string, cols []string, id string) {
	var ors []string
	var args []any
	for _, c := range cols {
		if a.s.HasColumn(r.Context(), view, c) {
			ors = append(ors, "lower(cast("+Ident(c)+" as varchar)) = lower(?)")
			args = append(args, id)
		}
	}
	res, err := a.s.Query(r.Context(), fmt.Sprintf("select * from %s where %s limit 1", Ident(view), strings.Join(ors, " or ")), args...)
	if err != nil {
		fail(w, 500, err)
		return
	}
	if len(res.Rows) == 0 {
		ok(w, nil)
		return
	}
	ok(w, res.Rows[0])
}

// featureTable resolves ?table= (a modality) or 400s.
func (a *api) featureTable(w http.ResponseWriter, r *http.Request) (string, Table, bool) {
	name, t, ok := a.s.M.FeatureTable(r.URL.Query().Get("table"))
	if !ok {
		fail(w, 400, fmt.Errorf("unknown feature table %q", name))
	}
	return name, t, ok
}

func (a *api) resultDef(name string) *Named {
	for i := range a.s.M.Results {
		if a.s.M.Results[i].Name == name {
			return &a.s.M.Results[i]
		}
	}
	return nil
}

// ---- obs

func (a *api) obsCount(w http.ResponseWriter, r *http.Request) {
	a.count(w, r, "obs", []string{a.s.M.Tables["obs"].ID})
}
func (a *api) obsList(w http.ResponseWriter, r *http.Request) {
	a.list(w, r, "obs", []string{a.s.M.Tables["obs"].ID}, 50, 100000)
}
func (a *api) obsFacets(w http.ResponseWriter, r *http.Request) {
	a.facets(w, r, "obs", []string{a.s.M.Tables["obs"].ID})
}
func (a *api) obsGet(w http.ResponseWriter, r *http.Request) {
	a.getOne(w, r, "obs", []string{a.s.M.Tables["obs"].ID}, r.PathValue("id"))
}

// ---- features

func (a *api) featuresSearch(w http.ResponseWriter, r *http.Request) {
	t := strings.TrimSpace(r.URL.Query().Get("q"))
	if t == "" {
		ok(w, &Result{Columns: []string{}, Rows: []map[string]any{}})
		return
	}
	table, _, okT := a.featureTable(w, r)
	if !okT {
		return
	}
	cols := a.s.M.SearchCols(table)
	var score, cond []string
	var args []any
	for _, c := range cols {
		score = append(score, "case when lower(cast("+Ident(c)+" as varchar)) = lower(?) then 0 when cast("+Ident(c)+" as varchar) ilike ? then 1 else 2 end")
		args = append(args, t, t+"%")
	}
	for _, c := range cols {
		cond = append(cond, "cast("+Ident(c)+" as varchar) ilike ?")
		args = append(args, "%"+t+"%")
	}
	limit := intParam(r, "limit", 20, 200)
	q := fmt.Sprintf("select *, (%s) as _score from %s where %s order by _score, length(cast(%s as varchar)), %s limit %d",
		strings.Join(score, " + "), Ident(table), strings.Join(cond, " or "), Ident(cols[0]), Ident(cols[0]), limit)
	res, err := a.s.Query(r.Context(), q, args...)
	if err != nil {
		fail(w, 500, err)
		return
	}
	ok(w, res)
}

func (a *api) featuresGet(w http.ResponseWriter, r *http.Request) {
	table, t, okT := a.featureTable(w, r)
	if !okT {
		return
	}
	a.getOne(w, r, table, append([]string{t.ID}, a.s.M.SearchCols(table)...), r.PathValue("id"))
}

// featuresWhere: rows of a feature table whose column equals a value (cross-modality ref lookup).
func (a *api) featuresWhere(w http.ResponseWriter, r *http.Request) {
	table, _, okT := a.featureTable(w, r)
	if !okT {
		return
	}
	col := r.URL.Query().Get("col")
	if !a.s.HasColumn(r.Context(), table, col) {
		fail(w, 400, fmt.Errorf("unknown column %q", col))
		return
	}
	res, err := a.s.Query(r.Context(), fmt.Sprintf("select * from %s where lower(cast(%s as varchar)) = lower(?) limit %d", Ident(table), Ident(col), intParam(r, "limit", 20, 200)), r.URL.Query().Get("value"))
	if err != nil {
		fail(w, 500, err)
		return
	}
	ok(w, res)
}

func (a *api) figure(w http.ResponseWriter, r *http.Request) {
	view := "fig_" + r.PathValue("id")
	if !a.s.HasView(view) {
		fail(w, 404, errors.New("unknown figure panel"))
		return
	}
	res, err := a.s.Query(r.Context(), fmt.Sprintf("select * from %s limit %d", Ident(view), intParam(r, "limit", 50000, 500000)))
	if err != nil {
		fail(w, 500, err)
		return
	}
	ok(w, res)
}

// ---- matrix / embedding / aggregates

func (a *api) matrixFeature(w http.ResponseWriter, r *http.Request) {
	view, okM := a.s.M.MatrixView(r.URL.Query().Get("matrix"))
	if !okM || !a.s.HasView(view) {
		fail(w, 404, errors.New("no such matrix in this package"))
		return
	}
	g := a.s.M.PrimaryGroup()
	withGroup := r.URL.Query().Get("group") != "0" && g != ""
	q := `select m.obs_id, m."value" as "value"`
	if withGroup {
		q += `, cast(o.` + Ident(g) + ` as varchar) as "group" from ` + Ident(view) + ` m join obs o on o.` + Ident(a.s.M.Tables["obs"].ID) + ` = m.obs_id`
	} else {
		q += ` from ` + Ident(view) + ` m`
	}
	res, err := a.s.Query(r.Context(), q+" where m.feature_id = ?", r.PathValue("id"))
	if err != nil {
		fail(w, 500, err)
		return
	}
	ok(w, res)
}

func (a *api) embedding(w http.ResponseWriter, r *http.Request) {
	view := "emb_" + r.PathValue("name")
	if !a.s.HasView(view) {
		fail(w, 404, errors.New("unknown embedding"))
		return
	}
	color := r.URL.Query().Get("color")
	sel := "e.obs_id, e.x, e.y"
	if color != "" {
		if !a.s.HasColumn(r.Context(), "obs", color) {
			fail(w, 400, fmt.Errorf("unknown column %q", color))
			return
		}
		sel += ", o." + Ident(color) + " as color"
	}
	res, err := a.s.Query(r.Context(), fmt.Sprintf("select %s from %s e join obs o on o.%s = e.obs_id", sel, Ident(view), Ident(a.s.M.Tables["obs"].ID)))
	if err != nil {
		fail(w, 500, err)
		return
	}
	ok(w, res)
}

func (a *api) aggFeatureGroup(w http.ResponseWriter, r *http.Request) {
	name := r.URL.Query().Get("name")
	if name == "" {
		name = "feature_group"
	}
	if !a.s.HasView("agg_" + name) {
		ok(w, &Result{Columns: []string{}, Rows: []map[string]any{}})
		return
	}
	res, err := a.s.Query(r.Context(), fmt.Sprintf(`select "group", n, mean, pct from %s where feature_id = ? order by mean desc`, Ident("agg_"+name)), r.PathValue("id"))
	if err != nil {
		fail(w, 500, err)
		return
	}
	ok(w, res)
}

// ---- results

func (a *api) resultView(w http.ResponseWriter, r *http.Request) (string, []string, bool) {
	d := a.resultDef(r.PathValue("name"))
	if d == nil {
		fail(w, 404, errors.New("unknown result table"))
		return "", nil, false
	}
	var text []string
	if d.FeatureCol != "" {
		text = append(text, d.FeatureCol)
	}
	if d.LabelCol != "" {
		text = append(text, d.LabelCol)
	}
	return "res_" + d.Name, text, true
}

func (a *api) resultsCount(w http.ResponseWriter, r *http.Request) {
	if v, t, ok := a.resultView(w, r); ok {
		a.count(w, r, v, t)
	}
}
func (a *api) resultsList(w http.ResponseWriter, r *http.Request) {
	if v, t, ok := a.resultView(w, r); ok {
		a.list(w, r, v, t, 50, 500000)
	}
}
func (a *api) resultsFacets(w http.ResponseWriter, r *http.Request) {
	if v, t, ok := a.resultView(w, r); ok {
		a.facets(w, r, v, t)
	}
}
func (a *api) resultsAll(w http.ResponseWriter, r *http.Request) {
	if v, t, ok := a.resultView(w, r); ok {
		if r.URL.Query().Get("limit") == "" {
			r.URL.RawQuery += "&limit=20000"
		}
		a.list(w, r, v, t, 20000, 500000)
	}
}

func (a *api) resultsForFeature(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	table, _, okT := a.featureTable(w, r)
	if !okT {
		return
	}
	out := []map[string]any{}
	for _, d := range a.s.M.Results {
		if d.FeatureCol == "" || (d.Features != "" && d.Features != table) || (d.Features == "" && table != "features") {
			continue
		}
		res, err := a.s.Query(r.Context(), fmt.Sprintf("select * from %s where %s = ? limit 200", Ident("res_"+d.Name), Ident(d.FeatureCol)), id)
		if err != nil {
			fail(w, 500, err)
			return
		}
		label := d.Name
		for _, c := range []string{"label"} {
			_ = c
		}
		for _, row := range res.Rows {
			row["_table"] = labelOf(a.s.M.Raw, d.Name, label)
			out = append(out, row)
		}
	}
	ok(w, out)
}

// labelOf reads results[name].label from the raw manifest (kept out of the typed struct on purpose).
func labelOf(raw json.RawMessage, name, def string) string {
	var m struct {
		Results []struct {
			Name  string `json:"name"`
			Label string `json:"label"`
		} `json:"results"`
	}
	if json.Unmarshal(raw, &m) == nil {
		for _, r := range m.Results {
			if r.Name == name && r.Label != "" {
				return r.Label
			}
		}
	}
	return def
}

// ---- sql

func (a *api) sql(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Query string `json:"query"`
		Limit int    `json:"limit"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&body); err != nil {
		fail(w, 400, err)
		return
	}
	res, err := a.s.SQL(r.Context(), body.Query, body.Limit)
	if err != nil {
		fail(w, 400, err)
		return
	}
	ok(w, res)
}

// ---- static

func noDirListing(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/") && r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		if strings.HasSuffix(r.URL.Path, ".parquet") {
			w.Header().Set("Cache-Control", "public, max-age=31536000, immutable")
		}
		next.ServeHTTP(w, r)
	})
}

var _ = context.Background
