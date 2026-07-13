"""Interfaz abstracta de modelos de valuación."""

from __future__ import annotations

from abc import ABC, abstractmethod

from opciones.modules.pricing_engine.types import Greeks, PricingInputs, PricingResult


class OptionPricingModel(ABC):
    """Las estrategias dependen de esta interfaz, no de BS concreto."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def price(self, inputs: PricingInputs) -> PricingResult:
        ...

    @abstractmethod
    def greeks(self, inputs: PricingInputs) -> Greeks:
        ...
