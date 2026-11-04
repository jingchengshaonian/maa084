import json
import os
import subprocess
import sys
from pathlib import Path

# 统一使用 utf-8 输出，避免 Windows 下中文日志编码报错
sys.stdout.reconfigure(encoding="utf-8")

current_script_dir = Path(__file__).resolve().parent
project_root_dir = current_script_dir.parent

# embeddable Python 的 _pth 不会把脚本所在目录加入 sys.path，需要手动补上
sys.path.insert(0, str(current_script_dir))

# 统一工作目录到项目根目录，Toolkit.init_option("./") 依赖相对路径
if Path.cwd() != project_root_dir:
    os.chdir(project_root_dir)

REQUIREMENTS_PATH = project_root_dir / "requirements.txt"
PIP_CONFIG_PATH = project_root_dir / "config" / "pip_config.json"
DEFAULT_PIP_CONFIG = {
    "enable_pip_install": True,
    "last_version": "unknown",
    "mirrors": [
        "https://pypi.tuna.tsinghua.edu.cn/simple",
        "https://mirrors.cloud.tencent.com/pypi/simple/",
        "https://mirrors.aliyun.com/pypi/simple/",
        "https://pypi.org/simple",
    ],
}


def read_pip_config() -> dict:
    config = dict(DEFAULT_PIP_CONFIG)
    if PIP_CONFIG_PATH.exists():
        try:
            config.update(json.loads(PIP_CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            print("[agent] 读取 pip 配置失败，使用默认配置")
    else:
        write_pip_config(config)
    return config


def write_pip_config(config: dict) -> None:
    PIP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PIP_CONFIG_PATH.write_text(
        json.dumps(config, indent=4, ensure_ascii=False), encoding="utf-8"
    )


def read_interface_version() -> str:
    for path in (
        project_root_dir / "interface.json",
        project_root_dir / "assets" / "interface.json",
    ):
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data.get("version", "unknown")
            except Exception:
                print(f"[agent] 读取版本失败: {path}")
                return "unknown"
    return "unknown"


def install_requirements(mirrors: list[str]) -> bool:
    for mirror in mirrors:
        print(f"[agent] 尝试从镜像安装依赖: {mirror}")
        try:
            subprocess.run(
                [
                    sys.executable, "-m", "pip", "install",
                    "-U", "-r", str(REQUIREMENTS_PATH),
                    "-i", mirror,
                    "--no-warn-script-location",
                ],
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            print(f"[agent] 镜像不可用: {mirror}")
    return False


def check_and_install_dependencies() -> None:
    """随包 Python 未预装第三方库，首次运行（或版本变化）时联网安装。"""
    config = read_pip_config()
    if not config.get("enable_pip_install", True):
        return

    version = read_interface_version()
    if version == config.get("last_version"):
        return

    if not REQUIREMENTS_PATH.exists():
        print(f"[agent] 未找到 {REQUIREMENTS_PATH}，跳过依赖安装")
        return

    print(f"[agent] 资源版本 {version} 与上次 {config.get('last_version')} 不一致，检查依赖")
    if install_requirements(config["mirrors"]):
        config["last_version"] = version
        write_pip_config(config)
        print("[agent] 依赖安装完成")
    else:
        print("[agent] 依赖安装失败，程序可能无法正常运行")


def agent():
    from maa.agent.agent_server import AgentServer
    from maa.toolkit import Toolkit

    import my_action
    import my_reco

    Toolkit.init_option("./")

    if len(sys.argv) < 2:
        print("Usage: python main.py <socket_id>")
        print("socket_id is provided by AgentIdentifier.")
        sys.exit(1)

    socket_id = sys.argv[-1]

    AgentServer.start_up(socket_id)
    AgentServer.join()
    AgentServer.shut_down()


if __name__ == "__main__":
    check_and_install_dependencies()
    agent()
