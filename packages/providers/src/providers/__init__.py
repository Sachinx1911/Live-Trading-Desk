"""Provider interfaces and adapters. Provider-specific code lives only here."""

from providers.fake import register as _register_fake

_register_fake()
