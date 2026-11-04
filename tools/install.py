from pathlib import Path

import shutil
import subprocess
import sys
import tempfile
import urllib.request

try:
    import jsonc
except ModuleNotFoundError as e:
    raise ImportError(
        "Missing dependency 'json-with-comments' (imported as 'jsonc').\n"
        f"Install it with:\n  {sys.executable} -m pip install json-with-comments\n"
        "Or add it to your project's requirements."
    ) from e

from configure import configure_ocr_model


working_dir = Path(__file__).parent.parent.resolve()
install_path = working_dir / Path("install")
version = len(sys.argv) > 1 and sys.argv[1] or "v0.0.1"

# the first parameter is self name
if sys.argv.__len__() < 4:
    print("Usage: python install.py <version> <os> <arch>")
    print("Example: python install.py v1.0.0 win x86_64")
    sys.exit(1)

os_name = sys.argv[2]
arch = sys.argv[3]

# 随包分发的官方 embeddable Python，需与 agent 依赖的版本保持一致
PYTHON_EMBED_VERSION = "3.12.10"


def get_dotnet_platform_tag():
    """自动检测当前平台并返回对应的dotnet平台标签"""
    if os_name == "win" and arch == "x86_64":
        platform_tag = "win-x64"
    elif os_name == "win" and arch == "aarch64":
        platform_tag = "win-arm64"
    elif os_name == "macos" and arch == "x86_64":
        platform_tag = "osx-x64"
    elif os_name == "macos" and arch == "aarch64":
        platform_tag = "osx-arm64"
    elif os_name == "linux" and arch == "x86_64":
        platform_tag = "linux-x64"
    elif os_name == "linux" and arch == "aarch64":
        platform_tag = "linux-arm64"
    else:
        print("Unsupported OS or architecture.")
        print("available parameters:")
        print("version: e.g., v1.0.0")
        print("os: [win, macos, linux, android]")
        print("arch: [aarch64, x86_64]")
        sys.exit(1)

    return platform_tag


def install_deps():
    if not (working_dir / "deps" / "bin").exists():
        print('Please download the MaaFramework to "deps" first.')
        print('请先下载 MaaFramework 到 "deps"。')
        sys.exit(1)

    if os_name == "android":
        shutil.copytree(
            working_dir / "deps" / "bin",
            install_path,
            dirs_exist_ok=True,
        )
        shutil.copytree(
            working_dir / "deps" / "share" / "MaaAgentBinary",
            install_path / "MaaAgentBinary",
            dirs_exist_ok=True,
        )
    else:
        shutil.copytree(
            working_dir / "deps" / "bin",
            install_path / "runtimes" / get_dotnet_platform_tag() / "native",
            ignore=shutil.ignore_patterns(
                "*MaaDbgControlUnit*",
                "*MaaThriftControlUnit*",
                "*MaaRpc*",
                "*MaaHttp*",
                "plugins",
                "*.node",
                "*MaaPiCli*",
            ),
            dirs_exist_ok=True,
        )
        shutil.copytree(
            working_dir / "deps" / "share" / "MaaAgentBinary",
            install_path / "libs" / "MaaAgentBinary",
            dirs_exist_ok=True,
        )
        shutil.copytree(
            working_dir / "deps" / "bin" / "plugins",
            install_path / "plugins" / get_dotnet_platform_tag(),
            dirs_exist_ok=True,
        )



def install_resource():

    configure_ocr_model()

    shutil.copytree(
        working_dir / "assets" / "resource",
        install_path / "resource",
        dirs_exist_ok=True,
    )
    shutil.copy2(
        working_dir / "assets" / "interface.json",
        install_path,
    )

    with open(install_path / "interface.json", "r", encoding="utf-8") as f:
        interface = jsonc.load(f)

    interface["version"] = version

    with open(install_path / "interface.json", "w", encoding="utf-8") as f:
        jsonc.dump(interface, f, ensure_ascii=False, indent=4)


def install_chores():
    shutil.copy2(
        working_dir / "README.md",
        install_path,
    )
    shutil.copy2(
        working_dir / "LICENSE",
        install_path,
    )
    # 用户端首次运行由 agent 自己 pip 安装依赖，需要把清单一起打包
    shutil.copy2(
        working_dir / "requirements.txt",
        install_path,
    )


def install_agent():
    shutil.copytree(
        working_dir / "agent",
        install_path / "agent",
        dirs_exist_ok=True,
    )

    # assets/interface.json 里是开发机路径，发布包需改写为随包 Python
    if os_name == "win":
        with open(install_path / "interface.json", "r", encoding="utf-8") as f:
            interface = jsonc.load(f)

        interface["agent"]["child_exec"] = r"{PROJECT_DIR}/python/python.exe"
        interface["agent"]["child_args"] = ["-u", r"{PROJECT_DIR}/agent/main.py"]

        with open(install_path / "interface.json", "w", encoding="utf-8") as f:
            jsonc.dump(interface, f, ensure_ascii=False, indent=4)


def install_embedded_python():
    """下载官方 embeddable Python 到 install/python，并放开 site-packages。"""
    if os_name != "win":
        return

    python_dir = install_path / "python"
    python_exe = python_dir / "python.exe"

    if not python_exe.exists():
        platform_tag = "amd64" if arch == "x86_64" else "arm64"
        url = (
            "https://www.python.org/ftp/python/"
            f"{PYTHON_EMBED_VERSION}/python-{PYTHON_EMBED_VERSION}-embed-{platform_tag}.zip"
        )
        print(f"Downloading embedded Python: {url}")
        python_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "python-embed.zip"
            urllib.request.urlretrieve(url, archive)
            shutil.unpack_archive(archive, python_dir)

    # embeddable 默认不加载第三方库，需要手动开启 site 并加入 Lib 目录
    pth_file = python_dir / f"python{PYTHON_EMBED_VERSION.replace('.', '')[:3]}._pth"
    if pth_file.exists():
        lines = [
            line.replace("#import site", "import site")
            for line in pth_file.read_text(encoding="utf-8").splitlines()
        ]
        for required in ("Lib", "Lib\\site-packages", "DLLs"):
            if required not in lines:
                lines.append(required)
        pth_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def install_pip():
    """给随包 embeddable Python 安装 pip，依赖由 agent 首次运行时自行安装。"""
    if os_name != "win":
        return

    python_dir = install_path / "python"
    site_packages = python_dir / "Lib" / "site-packages"
    if not (python_dir / "python.exe").exists():
        print("Embedded Python not found, skip pip installation.")
        return

    if (site_packages / "pip").exists():
        print("pip already bundled, skip.")
        return

    # CI 构建机可能是 ubuntu，无法执行 Windows 的 python.exe，
    # 因此用构建机的 pip 把纯 Python 的 pip 包直接放进随包 site-packages
    print("Installing pip into embedded Python ...")
    site_packages.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable, "-m", "pip", "install",
            "--target", str(site_packages),
            "--upgrade",
            "--no-warn-script-location",
            "pip",
        ],
        check=True,
    )


if __name__ == "__main__":
    install_deps()
    install_embedded_python()
    install_pip()
    install_resource()
    install_chores()
    install_agent()

    print(f"Install to {install_path} successfully.")
