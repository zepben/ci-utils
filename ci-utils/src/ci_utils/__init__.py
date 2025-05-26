import os
import sys
import click


class Environment:
    def __init__(self):
        self.verbose = False
        self.home = os.getcwd()

    def info(self, msg, *args):
        """Logs a message to stderr."""
        if args:
            msg %= args
        click.echo(msg, file=sys.stderr)

    def debug(self, msg, *args):
        """Logs a message to stderr only if verbose is enabled."""
        if self.verbose:
            self.log(msg, *args)

    def fail(self, msg, *args):
        """Logs an error to stdout and exits"""
        click.echo(msg, *args)
        raise Exception(msg)

    def warn(self, msg, *args):
        """Logs a warning to stdout"""
        print(" ctx.warn is not implemented yet!")
        pass


pass_environment = click.make_pass_decorator(Environment, ensure=True)
