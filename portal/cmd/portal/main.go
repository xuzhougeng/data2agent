// portal: serve, query and expose a Data2Agent contract package.
//
//	portal serve <package> [--addr :8080]
//	portal mcp   <package>            (stdio MCP server; see mcp.go)
package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/xuzhougeng/data2agent/portal/internal/portal"
)

func usage() {
	fmt.Fprintln(os.Stderr, "usage:\n  portal serve <package> [--addr :8080]\n  portal mcp <package>")
	os.Exit(2)
}

func main() {
	if len(os.Args) < 3 {
		usage()
	}
	cmd, pkg := os.Args[1], os.Args[2]
	fs := flag.NewFlagSet(cmd, flag.ExitOnError)
	addr := fs.String("addr", ":8080", "listen address")
	fs.Parse(os.Args[3:])

	store, err := portal.Open(pkg)
	if err != nil {
		log.Fatalf("open %s: %v", pkg, err)
	}
	switch cmd {
	case "serve":
		srv := &http.Server{Addr: *addr, Handler: portal.Handler(store), ReadHeaderTimeout: 10 * time.Second}
		log.Printf("%s: serving %s on http://%s/ (api at /api/)", store.M.ID, store.Pkg, *addr)
		log.Fatal(srv.ListenAndServe())
	case "mcp":
		if err := portal.ServeMCP(store); err != nil {
			log.Fatal(err)
		}
	default:
		usage()
	}
}
