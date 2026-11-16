"""Plugin tool: ask a question about an image using a vision-capable model.

Semantics differ from the built-in `image_to_text`:
  image_to_text  → "describe this image"   (general-purpose conversion)
  ask_image      → "answer this question"   (targeted QA)

Reuses ImageToTextTool for image resolution, vision config lookup, the
streaming call, and read-only semantics. Only prompt composition is new.

Import note: the plugin loader scans `dir(module)` for BaseTool subclasses
and instantiates every hit. A directly imported `ImageToTextTool` (even
under an `as` alias) is still a type object and would be re-registered
under its original name, colliding with the built-in tool. Importing the
*module* keeps a module object in this namespace, which the loader skips
(module objects are not `type`).
"""

from __future__ import annotations

from pydantic import Field

from openharness.tools import image_to_text_tool
from openharness.tools.base import ToolExecutionContext, ToolResult

_DESCRIPTION_PREFIX = "[Image description via "
_ANSWER_PREFIX = "[Image answer via "


class AskImageInput(image_to_text_tool.ImageToTextToolInput):
    """Image input plus a specific question to answer about it."""

    question: str = Field(
        description=(
            "The specific question to answer about the image, e.g. "
            "'What does the error dialog say?' or 'List all visible button labels.' "
            "The answer should be grounded in what is visibly present."
        ),
    )
    context: str | None = Field(
        default=None,
        description=(
            "Optional extra context to guide the answer, e.g. "
            "'This is a screenshot from a CI failure log.' or "
            "'Answer in JSON: {\"error\": str, \"line\": int}'."
        ),
    )


def _compose_question_prompt(arguments: AskImageInput) -> str:
    """Build a QA-oriented prompt from question + optional context."""
    parts = [
        "You are answering a question about an image. "
        "Answer precisely based on what is visibly present. "
        "If the image does not contain the information needed, say so explicitly.",
        "",
        f"Question: {arguments.question.strip()}",
    ]
    if arguments.context and arguments.context.strip():
        parts.extend(["", f"Additional context: {arguments.context.strip()}"])
    return "\n".join(parts)


class AskImageTool(image_to_text_tool.ImageToTextTool):
    """Ask a question about an image and return a grounded answer."""

    name = "ask_image"
    description = (
        "Ask a specific question about a local image using a vision-capable model. "
        "Use this when you need an answer grounded in the image content (e.g. "
        "'what does this error say?', 'which button is highlighted?', 'extract the "
        "table as JSON'). Prefer this over image_to_text for targeted questions; "
        "use image_to_text when you want a general description. Requires a configured "
        "vision model (vision.model + vision.api_key)."
    )
    input_model = AskImageInput

    async def execute(
        self,
        arguments: AskImageInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        # Collapse the QA prompt into `prompt`, then delegate to the original
        # implementation unchanged (image resolution, config lookup, streaming).
        merged = arguments.model_copy(
            update={"prompt": _compose_question_prompt(arguments)}
        )
        result = await super().execute(merged, context)
        return ToolResult(
            output=_rename_output(result.output),
            is_error=result.is_error,
            metadata=result.metadata,
        )


def _rename_output(output: str) -> str:
    """Relabel inherited image_to_text wording so errors point at ask_image."""
    if output.startswith("image_to_text failed:"):
        return output.replace("image_to_text failed:", "ask_image failed:", 1)
    if output.startswith(_DESCRIPTION_PREFIX):
        return _ANSWER_PREFIX + output[len(_DESCRIPTION_PREFIX):]
    return output
