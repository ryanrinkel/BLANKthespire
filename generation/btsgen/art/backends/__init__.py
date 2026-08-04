"""Built-in image backends. Importing this package registers them. null + procedural have no deps;
the openai backend also uses only stdlib (urllib), so it's safe to register here too and is simply
inert (available() == False) until an API key is set. Backends that need a heavy client (e.g. an SDK)
should instead register themselves on their own module import, so the dep isn't required to use the rest.
"""
from ..registry import register
from .null import NullBackend
from .openai import OpenAIImageBackend
from .procedural import ProceduralBackend

register(NullBackend())
register(ProceduralBackend())
register(OpenAIImageBackend())
