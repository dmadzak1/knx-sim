"""Entry point for `python -m knx_sim.cli` -- delegates to the same
main() the installed `knx-sim` console script uses."""

from knx_sim.cli.main import main

if __name__ == "__main__":
    main()
