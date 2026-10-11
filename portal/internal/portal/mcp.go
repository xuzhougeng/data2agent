package portal

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// ServeMCP exposes the Store over stdio MCP. Tool names match the API page: describe_tables, sql,
// search_features, get_obs, feature_summary. Every tool is read-only; results are JSON text.
func ServeMCP(s *Store) error {
	srv := mcp.NewServer(&mcp.Implementation{Name: "data2agent-portal", Title: s.M.Title, Version: "0.1"}, &mcp.ServerOptions{
		Instructions: fmt.Sprintf("Dataset %q (%s). Call describe_tables first to learn the tables, columns and roles; then use sql (DuckDB dialect, read-only) or the convenience tools. Views: obs, features, matrix (obs_id, feature_id, value; absent pairs are 0), emb_<name>, res_<name>, agg_<name>.", s.M.Title, s.M.ID),
	})

	type empty struct{}
	mcp.AddTool(srv, &mcp.Tool{Name: "describe_tables", Description: "Describe the dataset: title, kind, statistics, every table with its columns (name, label, type, role), matrices, embeddings, result tables and example SQL."},
		func(ctx context.Context, req *mcp.CallToolRequest, _ empty) (*mcp.CallToolResult, any, error) {
			return text(describe(s)), nil, nil
		})

	type sqlArgs struct {
		Query string `json:"query" jsonschema:"one read-only SELECT/WITH statement in DuckDB SQL over the views listed by describe_tables"`
		Limit int    `json:"limit,omitempty" jsonschema:"max rows to return (default 100, max 1000)"`
	}
	mcp.AddTool(srv, &mcp.Tool{Name: "sql", Description: "Run a read-only SQL query (DuckDB dialect) against the dataset views. Returns {columns, rows}."},
		func(ctx context.Context, req *mcp.CallToolRequest, a sqlArgs) (*mcp.CallToolResult, any, error) {
			if a.Limit <= 0 {
				a.Limit = 100
			}
			res, err := s.SQL(ctx, a.Query, a.Limit)
			if err != nil {
				return toolErr(err), nil, nil
			}
			return jsonText(res), nil, nil
		})

	type searchArgs struct {
		Query string `json:"query" jsonschema:"symbol, id or substring to search in the feature table"`
		Limit int    `json:"limit,omitempty" jsonschema:"max matches (default 20)"`
	}
	mcp.AddTool(srv, &mcp.Tool{Name: "search_features", Description: "Find features (genes, probes, proteins...) by symbol or id; exact and prefix matches rank first."},
		func(ctx context.Context, req *mcp.CallToolRequest, a searchArgs) (*mcp.CallToolResult, any, error) {
			if a.Limit <= 0 {
				a.Limit = 20
			}
			cols := searchCols(s.M)
			var score, cond []string
			var args []any
			for _, c := range cols {
				score = append(score, "case when lower(cast("+Ident(c)+" as varchar)) = lower(?) then 0 when cast("+Ident(c)+" as varchar) ilike ? then 1 else 2 end")
				args = append(args, a.Query, a.Query+"%")
			}
			for _, c := range cols {
				cond = append(cond, "cast("+Ident(c)+" as varchar) ilike ?")
				args = append(args, "%"+a.Query+"%")
			}
			q := fmt.Sprintf("select * exclude(_score) from (select *, (%s) as _score from features where %s order by _score, length(cast(%s as varchar)), %s limit %d)",
				strings.Join(score, " + "), strings.Join(cond, " or "), Ident(cols[0]), Ident(cols[0]), a.Limit)
			res, err := s.Query(ctx, q, args...)
			if err != nil {
				return toolErr(err), nil, nil
			}
			return jsonText(res), nil, nil
		})

	type idArgs struct {
		ID string `json:"id" jsonschema:"observation id (cell / sample id)"`
	}
	mcp.AddTool(srv, &mcp.Tool{Name: "get_obs", Description: "Return one observation (cell, sample...) row with all its annotations."},
		func(ctx context.Context, req *mcp.CallToolRequest, a idArgs) (*mcp.CallToolResult, any, error) {
			res, err := s.Query(ctx, fmt.Sprintf("select * from obs where %s = ? limit 1", Ident(s.M.Tables["obs"].ID)), a.ID)
			if err != nil {
				return toolErr(err), nil, nil
			}
			if len(res.Rows) == 0 {
				return text("no observation with id " + a.ID), nil, nil
			}
			return jsonText(res.Rows[0]), nil, nil
		})

	type featArgs struct {
		Feature string `json:"feature" jsonschema:"feature symbol or id"`
	}
	mcp.AddTool(srv, &mcp.Tool{Name: "feature_summary", Description: "Summarise one feature: its annotation row, per-group mean and fraction expressing (from the aggregate table), and every hit in result tables (markers, differential expression)."},
		func(ctx context.Context, req *mcp.CallToolRequest, a featArgs) (*mcp.CallToolResult, any, error) {
			cols := append([]string{s.M.Tables["features"].ID}, searchCols(s.M)...)
			var ors []string
			var args []any
			for _, c := range cols {
				ors = append(ors, "lower(cast("+Ident(c)+" as varchar)) = lower(?)")
				args = append(args, a.Feature)
			}
			row, err := s.Query(ctx, fmt.Sprintf("select * from features where %s limit 1", strings.Join(ors, " or ")), args...)
			if err != nil {
				return toolErr(err), nil, nil
			}
			if len(row.Rows) == 0 {
				return text("no feature matches " + a.Feature), nil, nil
			}
			out := map[string]any{"feature": row.Rows[0]}
			id := fmt.Sprint(row.Rows[0][s.M.Tables["features"].ID])
			if s.HasView("agg_feature_group") {
				if agg, err := s.Query(ctx, `select "group", n, mean, pct from agg_feature_group where feature_id = ? order by mean desc`, id); err == nil {
					out["by_group"] = agg.Rows
				}
			}
			hits := []map[string]any{}
			for _, r := range s.M.Results {
				if r.FeatureCol == "" {
					continue
				}
				if res, err := s.Query(ctx, fmt.Sprintf("select * from %s where %s = ? limit 50", Ident("res_"+r.Name), Ident(r.FeatureCol)), id); err == nil {
					for _, h := range res.Rows {
						h["_table"] = r.Name
						hits = append(hits, h)
					}
				}
			}
			out["result_hits"] = hits
			return jsonText(out), nil, nil
		})

	return srv.Run(context.Background(), &mcp.StdioTransport{})
}

func searchCols(m *Manifest) []string {
	var cols []string
	for _, c := range m.Tables["features"].Columns {
		if c.Search {
			cols = append(cols, c.Name)
		}
	}
	if len(cols) == 0 {
		cols = []string{m.Tables["features"].ID}
	}
	return cols
}

// describe builds a compact, agent-oriented description from the raw manifest.
func describe(s *Store) string {
	var raw map[string]any
	_ = json.Unmarshal(s.M.Raw, &raw)
	pick := func(keys ...string) map[string]any {
		out := map[string]any{}
		for _, k := range keys {
			if v, ok := raw[k]; ok {
				out[k] = v
			}
		}
		return out
	}
	d := pick("id", "title", "description", "kind", "organism", "stats", "license", "source", "methods")
	tables := map[string]any{}
	for name, t := range s.M.Tables {
		cols := []map[string]any{}
		for _, c := range t.Columns {
			if c.Role == "hidden" {
				continue
			}
			col := map[string]any{"name": c.Name, "label": c.Label, "dtype": c.Dtype, "role": c.Role}
			if c.PrimaryGroup {
				col["primary_group"] = true
			}
			cols = append(cols, col)
		}
		tables[name] = map[string]any{"label": t.Label, "rows": t.Rows, "id": t.ID, "columns": cols}
	}
	d["tables"] = tables
	views := []string{}
	for _, v := range s.M.Views() {
		views = append(views, v.Name)
	}
	d["views"] = views
	d["matrices"] = raw["matrices"]
	d["embeddings"] = raw["embeddings"]
	d["results"] = raw["results"]
	d["aggregates"] = raw["aggregates"]
	g := s.M.PrimaryGroup()
	ex := []string{"select * from obs limit 5", "select * from features limit 5"}
	if g != "" {
		ex = append(ex, fmt.Sprintf(`select %s, count(*) as n from obs group by 1 order by n desc`, Ident(g)))
		if s.HasView("matrix") {
			ex = append(ex, fmt.Sprintf(`select o.%s as grp, avg(m."value") as mean_value, count(*) as n_nonzero from matrix m join obs o on o.%s = m.obs_id where m.feature_id = '<feature_id>' group by 1 order by 2 desc`, Ident(g), Ident(s.M.Tables["obs"].ID)))
		}
	}
	d["example_sql"] = ex
	d["notes"] = "matrix stores non-zero values only; join obs/features on obs_id/feature_id; use search_features to resolve symbols to feature_id."
	b, _ := json.MarshalIndent(d, "", " ")
	return string(b)
}

func text(t string) *mcp.CallToolResult {
	return &mcp.CallToolResult{Content: []mcp.Content{&mcp.TextContent{Text: t}}}
}

func jsonText(v any) *mcp.CallToolResult {
	b, _ := json.Marshal(v)
	return text(string(b))
}

func toolErr(err error) *mcp.CallToolResult {
	return &mcp.CallToolResult{IsError: true, Content: []mcp.Content{&mcp.TextContent{Text: err.Error()}}}
}
