import click
import sys
from pathlib import Path

# Add project root to path so we can import tools as modules if needed
sys.path.insert(0, str(Path(__file__).parents[2]))

@click.group()
@click.version_option(version="2.0.0")
def cli():
    """Dedupe Library Management CLI"""
    pass

@cli.command(context_settings=dict(ignore_unknown_options=True, help_option_names=[]))
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def scan(args):
    """Scan a library volume (legacy wrapper)"""
    from tools.integrity.scan import scan as scan_cmd
    # If -h or --help is in args, we want to let the underlying command handle it
    # but Click might intercept it before we get here.
    # That's why we use help_option_names=[]
    sys.argv = ['dedupe scan'] + list(args)
    scan_cmd()

@cli.command(context_settings=dict(ignore_unknown_options=True, help_option_names=[]))
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def recommend(args):
    """Generate deduplication recommendations (legacy wrapper)"""
    from tools.decide.recommend import recommend as recommend_cmd
    sys.argv = ['dedupe recommend'] + list(args)
    recommend_cmd()

@cli.command(context_settings=dict(ignore_unknown_options=True, help_option_names=[]))
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def apply(args):
    """Execute deduplication plan (legacy wrapper)"""
    from tools.decide.apply import apply as apply_cmd
    sys.argv = ['dedupe apply'] + list(args)
    apply_cmd()

if __name__ == "__main__":
    cli()
