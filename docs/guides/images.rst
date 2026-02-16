Images
======

Attach local images to a Codex CLI turn with acodex by passing a structured input list.

When to use this page
---------------------

- Your prompt needs a screenshot, diagram, or photo as context.
- You want to combine text and images in a single turn.

This page uses typed structured output via ``output_type`` (Structured-output extra). Install it first:
``uv add "acodex[structured-output]"``.

.. code-block:: python

   from pydantic import BaseModel

   from acodex import Codex
   from acodex.types.input import UserInputLocalImage, UserInputText

   class ImageDescription(BaseModel):
       description: str

   thread = Codex().start_thread()
   turn = thread.run(
       [
           UserInputText(text="Describe this image."),
           UserInputLocalImage(path="./ui.png"),
       ],
       output_type=ImageDescription,
   )
   print(turn.structured_response.description)

The ``Input`` type accepted by ``run`` / ``run_streamed`` is either a plain string or a list of
``UserInput`` entries (text + local images).
