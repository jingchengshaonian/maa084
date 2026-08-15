import json
import re

from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context


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
