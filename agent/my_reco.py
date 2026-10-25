import json
import re
import traceback

from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context


_MAP_NODES: list[dict] = []


def get_map_nodes() -> list[dict]:
    """返回最近一次 GetMapNode 识别到的节点类型与分布。"""
    return list(_MAP_NODES)


@AgentServer.custom_recognition("OcrCompareCount")
class OcrCompareCount(CustomRecognition):
    """
    OCR 识别界面中的数字，与目标值比较，达标时返回命中。

    参数格式:
    {
        "target": 3,               // 目标次数
        "roi": [x, y, w, h],       // 数字所在区域
        "expected": "\\d+",        // OCR 期望的正则，默认匹配任意数字
        "compare": "ge"            // 比较方式: ge(>=) le(<=) gt(>) lt(<) eq(==)
    }

    命中条件（默认 ge）: 识别到的数字 >= target
    """

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ):
        try:
            params = json.loads(argv.custom_recognition_param) if argv.custom_recognition_param else {}
            target = params.get("target", 0)
            roi = params.get("roi", [716,305,65,35])
            expected = params.get("expected", "\\d+")
            compare = params.get("compare", "ge")
            print(f"[OcrCompareCount] 参数: target={target}, roi={roi}, expected={expected}, compare={compare}")

            # 用内部 OCR 节点识别数字
            reco_detail = context.run_recognition(
                "OcrCompareCount_OCR",
                argv.image,
                pipeline_override={
                    "OcrCompareCount_OCR": {
                        "recognition": {
                            "type": "OCR",
                            "param": {
                                "roi": roi,
                                "expected": [expected],
                                "threshold": 0.3
                            }
                        }
                    }
                }
            )

            if not reco_detail or not reco_detail.hit:
                print(f"[OcrCompareCount] OCR未识别到内容, reco_detail={reco_detail}")
                return None

            text = reco_detail.best_result.text
            print(f"[OcrCompareCount] OCR原始识别: '{text}'")

            # 从识别文本中提取数字
            match = re.search(r"\d+", text)
            if not match:
                print(f"[OcrCompareCount] 文本中未找到数字: '{text}'")
                return None

            current = int(match.group())
            print(f"[OcrCompareCount] 提取数字: {current}, 比较: {current} {compare} {target}")

            # 比较运算
            ops = {
                "ge": current >= target,
                "le": current <= target,
                "gt": current > target,
                "lt": current < target,
                "eq": current == target
            }

            result = ops.get(compare, False)
            print(f"[OcrCompareCount] 比较结果: {result}")

            if result:
                return CustomRecognition.AnalyzeResult(
                    box=reco_detail.box,
                    detail=f"OCR识别: {current} {compare} {target} -> 命中"
                )

            return None

        except Exception as e:
            import traceback
            print(f"[OcrCompareCount] 识别失败: {e}")
            print(traceback.format_exc())
            return None


@AgentServer.custom_recognition("GetMapNode")
class GetMapNode(CustomRecognition):
    """
    识别当前镜牢层地图上的全部节点类型与分布。

    参数格式:
    {
        "roi": [x, y, w, h],            // 整张地图扫描区域（可选，默认全屏）
        "nodes": [
            {
                "type": "战斗",          // 节点类型名（用于后续分支/权重）
                "template": "xxx.png",   // image 相对路径
                "threshold": 0.85        // 可选，默认 0.85
            }
        ],
        "expected_type": "商店"          // 可选。指定后仅该类型存在时命中，
                                        // 用于后续"按类型分支"复用同一函数
    }

    命中后结果缓存在模块级 _MAP_NODES，
    后续"连接识别/权重选择"节点可调用 get_map_nodes() 读取，无需重复截图。

    返回的 detail["nodes"] 示例:
    [
        {"type": "路线1", "box": [520, 300, 46, 42], "score": 0.9312},
        {"type": "路线2", "box": [700, 480, 42, 44], "score": 0.8621}
    ]
    """

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ):
        global _MAP_NODES
        try:
            params = json.loads(argv.custom_recognition_param) if argv.custom_recognition_param else {}
            map_roi = params.get("roi", [])
            node_defs = params.get("nodes", [])
            expected_type = params.get("expected_type")

            print(f"[GetMapNode] 参数: roi={map_roi}, nodes={len(node_defs)}, expected_type={expected_type}")

            found: list[dict] = []

            for i, node_def in enumerate(node_defs):
                node_type = node_def.get("type", f"节点{i}")
                template = node_def.get("template")
                threshold = node_def.get("threshold", 0.85)
                roi = node_def.get("roi") or map_roi

                if not template:
                    print(f"[GetMapNode] 节点 '{node_type}' 缺少 template，跳过")
                    continue

                reco_param = {
                    "template": template,
                    "threshold": threshold,
                }
                if roi:
                    reco_param["roi"] = roi

                reco_detail = context.run_recognition(
                    f"GetMapNode_TM_{i}",
                    argv.image,
                    pipeline_override={
                        f"GetMapNode_TM_{i}": {
                            "recognition": {
                                "type": "TemplateMatch",
                                "param": reco_param,
                            }
                        }
                    },
                )

                if not reco_detail or not reco_detail.hit:
                    print(f"[GetMapNode] 类型 '{node_type}' 未识别到节点")
                    continue

                for res in reco_detail.filtered_results:
                    box = list(res.box)
                    score = round(float(res.score), 4)
                    found.append({"type": node_type, "box": box, "score": score})
                    print(f"[GetMapNode] 识别到节点: type={node_type}, box={box}, score={score}")

            _MAP_NODES = sorted(found, key=lambda item: (item["box"][0], item["box"][1]))
            print(f"[GetMapNode] 共识别到 {len(_MAP_NODES)} 个节点: {_MAP_NODES}")

            if not _MAP_NODES:
                print("[GetMapNode] 未识别到任何节点")
                return None

            if expected_type:
                matched = [n for n in _MAP_NODES if n["type"] == expected_type]
                if not matched:
                    print(f"[GetMapNode] 未找到期望类型 '{expected_type}'")
                    return None
                print(f"[GetMapNode] 期望类型 '{expected_type}' 匹配: {matched}")
                return CustomRecognition.AnalyzeResult(
                    box=matched[0]["box"],
                    detail={"nodes": _MAP_NODES, "expected_type": expected_type, "matched": matched},
                )

            return CustomRecognition.AnalyzeResult(
                box=_MAP_NODES[0]["box"],
                detail={"nodes": _MAP_NODES, "count": len(_MAP_NODES)},
            )

        except Exception as e:
            print(f"[GetMapNode] 识别失败: {e}")
            print(traceback.format_exc())
            return None
