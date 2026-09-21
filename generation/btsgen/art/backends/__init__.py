"""Built-in image backends. Importing this package registers them. null + procedural have no deps;
the openai, openrouter and openai_images (Gemini / xAI) backends also use only stdlib (urllib), so it's
safe to register them here too and they are simply inert (available() == False) until an API key is set.
Backends that need a heavy client (e.g. an SDK) should instead register themselves on their own module
import, so the dep isn't required to use the rest.
"""
from ..registry import register
from .null import NullBackend
from .openai import OpenAIImageBackend
from .openai_images import OpenAIImagesBackend
from .openrouter import OpenRouterImageBackend
from .procedural import ProceduralBackend

register(NullBackend())
register(ProceduralBackend())
register(OpenAIImageBackend())
register(OpenRouterImageBackend())
# One generic OpenAI-shaped /images/generations backend per preset row: BYOK art on a Gemini or an
# xAI key. Keyless here, so both are inert on the server until GEMINI_API_KEY / XAI_API_KEY is set.
register(OpenAIImagesBackend("gemini"))
register(OpenAIImagesBackend("xai"))
