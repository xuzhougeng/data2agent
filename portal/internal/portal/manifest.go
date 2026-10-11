// Package portal serves a Data2Agent contract package: static site + /api/* named queries + MCP.
package portal

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

type Column struct {
	Name         string `json:"name"`
	Label        string `json:"label"`
	Dtype        string `json:"dtype"`
	Role         string `json:"role"`
	PrimaryGroup bool   `json:"primary_group"`
	Search       bool   `json:"search"`
}

type Table struct {
	Path    string   `json:"path"`
	Rows    int64    `json:"rows"`
	ID      string   `json:"id"`
	Label   string   `json:"label"`
	Columns []Column `json:"columns"`
}

type Shard struct {
	Path string `json:"path"`
}

type Matrix struct {
	Name     string  `json:"name"`
	Path     string  `json:"path"`
	Features string  `json:"features"` // feature table (modality); "" means "features"
	Shards   []Shard `json:"shards"`
}

type Named struct {
	Name       string   `json:"name"`
	ID         string   `json:"id"` // figure panels use id instead of name
	Path       string   `json:"path"`
	Features   string   `json:"features"`
	Matrix     string   `json:"matrix"` // aggregates: the matrix they summarise
	FeatureCol string   `json:"feature_col"`
	LabelCol   string   `json:"label_col"`
	Columns    []Column `json:"columns"`
}

type Figure struct {
	ID     string  `json:"id"`
	Panels []Named `json:"panels"`
}

type Manifest struct {
	ID         string           `json:"id"`
	Title      string           `json:"title"`
	Tables     map[string]Table `json:"tables"`
	Matrices   []Matrix         `json:"matrices"`
	Embeddings []Named          `json:"embeddings"`
	Results    []Named          `json:"results"`
	Aggregates []Named          `json:"aggregates"`
	Figures    []Figure         `json:"figures"`
	Raw        json.RawMessage  `json:"-"`
}

// FeatureTable resolves a modality name ("" = "features") to its table; ok is false for tables no matrix is over.
func (m *Manifest) FeatureTable(name string) (string, Table, bool) {
	if name == "" {
		name = "features"
	}
	t, ok := m.Tables[name]
	if !ok {
		return name, t, false
	}
	if name == "features" {
		return name, t, true
	}
	for _, x := range m.Matrices {
		if x.Features == name {
			return name, t, true
		}
	}
	return name, t, false
}

// SearchCols lists the searchable columns of a feature table (its id when none is flagged).
func (m *Manifest) SearchCols(table string) []string {
	var cols []string
	for _, c := range m.Tables[table].Columns {
		if c.Search {
			cols = append(cols, c.Name)
		}
	}
	if len(cols) == 0 {
		cols = []string{m.Tables[table].ID}
	}
	return cols
}

// MatrixView maps a matrix name ("" = first) to its view name; ok is false for unknown names.
func (m *Manifest) MatrixView(name string) (string, bool) {
	for i, x := range m.Matrices {
		if name == "" || x.Name == name {
			if i == 0 {
				return "matrix", true
			}
			return "matrix_" + x.Name, true
		}
	}
	return "", false
}

func LoadManifest(pkg string) (*Manifest, error) {
	b, err := os.ReadFile(filepath.Join(pkg, "manifest.json"))
	if err != nil {
		return nil, err
	}
	var m Manifest
	if err := json.Unmarshal(b, &m); err != nil {
		return nil, fmt.Errorf("manifest.json: %w", err)
	}
	if _, ok := m.Tables["obs"]; !ok {
		return nil, fmt.Errorf("manifest.json: tables.obs missing")
	}
	if _, ok := m.Tables["features"]; !ok {
		return nil, fmt.Errorf("manifest.json: tables.features missing")
	}
	m.Raw = b
	return &m, nil
}

// PrimaryGroup returns the obs column flagged primary_group, or "".
func (m *Manifest) PrimaryGroup() string {
	for _, c := range m.Tables["obs"].Columns {
		if c.PrimaryGroup {
			return c.Name
		}
	}
	return ""
}

// View describes one SQL view the store exposes: name -> parquet source(s).
type View struct {
	Name  string
	Paths []string
}

// Views lists every view with the same names the browser-side api.static.js uses.
func (m *Manifest) Views() []View {
	var out []View
	for name, t := range m.Tables {
		out = append(out, View{Name: name, Paths: []string{t.Path}})
	}
	for i, x := range m.Matrices {
		name := "matrix"
		if i > 0 {
			name = "matrix_" + x.Name
		}
		v := View{Name: name}
		if len(x.Shards) > 0 {
			for _, s := range x.Shards {
				v.Paths = append(v.Paths, s.Path)
			}
		} else {
			v.Paths = []string{x.Path}
		}
		out = append(out, v)
	}
	for _, e := range m.Embeddings {
		out = append(out, View{Name: "emb_" + e.Name, Paths: []string{e.Path}})
	}
	for _, r := range m.Results {
		out = append(out, View{Name: "res_" + r.Name, Paths: []string{r.Path}})
	}
	for _, g := range m.Aggregates {
		out = append(out, View{Name: "agg_" + g.Name, Paths: []string{g.Path}})
	}
	for _, f := range m.Figures {
		for _, p := range f.Panels {
			out = append(out, View{Name: "fig_" + p.ID, Paths: []string{p.Path}})
		}
	}
	return out
}
