import os
import re
import subprocess as sub
import sys
from importlib.metadata import PackageNotFoundError, version
from venv import EnvBuilder  # CORE_VENV_DEPS

try:
    dist_name = __name__
    __version__ = version(dist_name)
except PackageNotFoundError:
    __version__ = "unknown"
finally:
    del version, PackageNotFoundError


class VenvrBuilder(EnvBuilder):
    """Builder class for venvr"""

    def __init__(
        self,
        system_site_packages=False,
        *args,
        convert_to_venvr=False,
        r_system_site_packages=False,
        **kwds
    ):
        super().__init__(system_site_packages, *args, **kwds)
        self.convert_to_venvr = convert_to_venvr
        self.r_system_site_packages = r_system_site_packages

    def create(self, env_dir):
        """
        Create or convert a virtual environment in a directory.

        :param env_dir: The target directory to create an environment in.

        """
        if self.convert_to_venvr:
            env_dir = os.path.abspath(env_dir)
            cfg_path = os.path.join(env_dir, "pyvenv.cfg")
            if not os.path.exists(cfg_path):
                raise ValueError(
                    "This doesn't look like a Python virtual env: %s" % env_dir
                )
            context = self.ensure_directories(env_dir)
            context.cfg_path = cfg_path
            self.create_configuration(context, convert=True)
            self.post_setup(context)  # skip other steps
        else:
            super().create(env_dir)

    def create_configuration(self, context, convert=False):
        """
        Create a configuration file indicating where the environment's Python
        and R were copied from, and whether the system site-packages should be
        made available in the environment.

        :param context: The information for the environment creation request
                        being processed.
        """
        if not convert:
            super().create_configuration(context)

        if not hasattr(context, "r_home"):
            info = get_r_info()
            context.r_home = info["R_HOME"]
            context.r_exec = info["R"]
            context.rscript_exec = info["Rscript"]
            context.r_version = info["version"]

        with open(context.cfg_path, "a", encoding="utf-8") as f:
            f.write("\nR-home = %s\n" % context.r_home)
            if self.r_system_site_packages:
                incl = "true"
            else:
                incl = "false"
            f.write("R-include-system-packages = %s\n" % incl)
            f.write("R-version = %s\n" % ".".join(context.r_version))

    def post_setup(self, context):
        """
        Setup R stuff.

        :param context: The information for the environment creation request
                        being processed.
        """
        # --- ensure_directories() ---

        context.lib_name = libdir = "Lib" if sys.platform == "win32" else "lib"
        r_libdir = "R" + ".".join(context.r_version[:2])
        libpath = os.path.join(context.env_dir, libdir, r_libdir)
        if not os.path.exists(libpath):
            os.makedirs(libpath)
        elif os.path.islink(libpath) or os.path.isfile(libpath):
            raise ValueError("Unable to create directory %r" % libpath)

        # --- setup_r() ---

        copier = self.symlink_or_copy
        for executable in (context.r_exec, context.rscript_exec):
            suffix = os.path.basename(executable)
            copier(executable, os.path.join(context.bin_path, suffix))

        # --- setup_scripts() ---

        path = os.path.abspath(os.path.dirname(__file__))
        srcfile = os.path.join(path, "scripts", "common", "activate")
        dstfile = os.path.join(context.bin_path, "activate")
        with open(srcfile) as file:
            r_script = file.read()
        r_script = self.replace_variables(r_script, context)
        with open(dstfile, "r+") as file:
            py_script = file.read()
            py_script = re.sub(r"\bdeactivate\b", "deactivate_py", py_script)
            script = py_script + r_script
            file.seek(0)
            file.write(script)

    def replace_variables(self, text, context):
        """
        Replace variable placeholders in script text with context-specific
        variables.

        Return the text passed in , but with variables replaced.

        :param text: The text in which to replace placeholder variables.
        :param context: The information for the environment creation request
                        being processed.
        """
        text = super().replace_variables(text, context)
        if "__VENVR_" in text:
            incl = "true" if self.r_system_site_packages else "false"
            text = text.replace("__VENVR_SYSTEM_PACKAGES__", incl)
            text = text.replace("__VENVR_R_HOME__", context.r_home)
            text = text.replace("__VENVR_PY_EXEC__", context.python_exe)
            text = text.replace("__VENVR_LIB_NAME__", context.lib_name)
        return text


def get_r_info():
    """
    Get information about the R installation and locate its binaries.

    :param context: The information for the environment creation request
                    being processed.
    """
    r_home = sub.check_output(["R", "RHOME"], text=True).rstrip("\n")
    r_bin_path = os.path.join(r_home, "bin")
    if sys.platform == "win32" and "64 bit" in sys.version:
        r_bin_path = os.path.join(r_bin_path, "x64")

    r_exec = os.path.join(r_bin_path, "R")
    rscript_exec = os.path.join(r_bin_path, "Rscript")
    if not (os.path.exists(r_exec) and os.path.exists(rscript_exec)):
        raise ValueError("Could not find the R or Rscript executable.")

    cat_rv = 'cat(R.version$major, R.version$minor, sep=".")'
    rv = sub.check_output([rscript_exec, "--vanilla", "-e", cat_rv], text=True)
    if re.match(r"\d+\.\d+\..+", rv) is None:
        raise ValueError("Invalid R version: '%s'" % rv)

    res = {
        "R_HOME": r_home,
        "R": r_exec,
        "Rscript": rscript_exec,
        "version": rv.split("."),
    }
    return res


def create(
    env_dir,
    system_site_packages=False,
    clear=False,
    symlinks=False,
    with_pip=False,
    prompt=None,
    # upgrade_deps=False,
    convert_to_venvr=False,
    r_system_site_packages=False,
):
    """Create a virtual environment in a directory."""
    builder = VenvrBuilder(
        system_site_packages=system_site_packages,
        clear=clear,
        symlinks=symlinks,
        with_pip=with_pip,
        prompt=prompt,
        # upgrade_deps=upgrade_deps,
        convert_to_venvr=convert_to_venvr,
        r_system_site_packages=r_system_site_packages,
    )
    builder.create(env_dir)


def main(args=None):
    compatible = True
    if sys.version_info < (3, 3):
        compatible = False
    elif not hasattr(sys, "base_prefix"):
        compatible = False
    if not compatible:
        raise ValueError("This script is only for use with Python >= 3.3")

    import argparse

    parser = argparse.ArgumentParser(
        prog=__name__,
        description="Creates integrated virtual "
        "environments for Python and "
        "R in one or more target "
        "directories.",
        epilog="Once an environment has been "
        "created, you may wish to "
        "activate it, e.g. by "
        "sourcing an activate script "
        "in its bin directory.",
    )
    parser.add_argument(
        "dirs",
        metavar="ENV_DIR",
        nargs="+",
        help="A directory to create the environment in.",
    )
    parser.add_argument(
        "-R",
        "--convert-to-venvr",
        default=False,
        action="store_true",
        dest="convert",
        help="Convert an existing Python virtual environment " "to a Python/R one.",
    )
    parser.add_argument(
        "--system-site-packages",
        nargs="?",
        const="both",
        type=str.lower,
        choices=["python", "r", "both", "none"],
        dest="system_site",
        help="Give the virtual environment access to the "
        "system site-packages dirs (case insensitive).",
    )
    if os.name == "nt":
        use_symlinks = False
    else:
        use_symlinks = True
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--symlinks",
        default=use_symlinks,
        action="store_true",
        dest="symlinks",
        help="Try to use symlinks rather than copies, "
        "when symlinks are not the default for "
        "the platform.",
    )
    group.add_argument(
        "--copies",
        default=not use_symlinks,
        action="store_false",
        dest="symlinks",
        help="Try to use copies rather than symlinks, "
        "even when symlinks are the default for "
        "the platform.",
    )
    parser.add_argument(
        "--clear",
        default=False,
        action="store_true",
        dest="clear",
        help="Delete the contents of the "
        "environment directory if it "
        "already exists, before "
        "environment creation.",
    )
    parser.add_argument(
        "--upgrade",
        default=False,
        action="store_true",
        dest="upgrade",
        help="Upgrade the environment "
        "directory to use this version "
        "of Python, assuming Python "
        "has been upgraded in-place.",
    )
    parser.add_argument(
        "--without-pip",
        dest="with_pip",
        default=True,
        action="store_false",
        help="Skips installing or upgrading pip in the "
        "virtual environment (pip is bootstrapped "
        "by default)",
    )
    parser.add_argument(
        "--prompt",
        help="Provides an alternative prompt prefix for " "this environment.",
    )
    # parser.add_argument(
    #     "--upgrade-deps",
    #     default=False,
    #     action="store_true",
    #     dest="upgrade_deps",
    #     help="Upgrade core dependencies: {} to the latest "
    #     "version in PyPI".format(" ".join(CORE_VENV_DEPS)),
    # )
    options = parser.parse_args(args)
    err_msg = "you cannot supply --{} and --clear together."
    if options.convert and options.clear:
        raise ValueError(err_msg.format("convert-to-venvr"))
    if options.upgrade and options.clear:
        raise ValueError(err_msg.format("upgrade"))
    builder = VenvrBuilder(
        convert_to_venvr=options.convert,
        system_site_packages=options.system_site in ("both", "python"),
        r_system_site_packages=options.system_site in ("both", "r"),
        clear=options.clear,
        symlinks=options.symlinks,
        upgrade=options.upgrade,
        with_pip=options.with_pip,
        prompt=options.prompt,
        # upgrade_deps=options.upgrade_deps,
    )
    for d in options.dirs:
        builder.create(d)


if __name__ == "__main__":
    rc = 1
    try:
        main()
        rc = 0
    except Exception as e:
        print("Error: %s" % e, file=sys.stderr)
    sys.exit(rc)
