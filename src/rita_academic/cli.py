"""Ponto de entrada: `rita-academic --transport stdio|streamable-http`."""

from __future__ import annotations

import argparse
import logging
import sys

from rita_academic.config import Settings


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="rita-academic", description="Servidor MCP acadêmico pessoal.")
    ap.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    ap.add_argument("--library", help="Pasta raiz da biblioteca (equivale a RITA_LIBRARY_ROOT).")
    ap.add_argument("--host", help="Host HTTP (padrão RITA_HTTP_HOST ou 127.0.0.1).")
    ap.add_argument("--port", type=int, help="Porta HTTP (padrão RITA_HTTP_PORT ou 8765).")
    ap.add_argument("--stateless", action="store_true",
                    help="HTTP sem sessão persistente (para clientes que reconectam a cada chamada).")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    # Em stdio, stdout é o canal do protocolo: logs vão para stderr.
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, stream=sys.stderr,
                        format="%(levelname)s %(name)s: %(message)s")

    settings = Settings.from_env(library_root=args.library)
    from rita_academic.server import build_server

    server = build_server(settings)
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="streamable-http", host=args.host or settings.http_host,
                   port=args.port or settings.http_port, stateless_http=args.stateless)


if __name__ == "__main__":
    main()
