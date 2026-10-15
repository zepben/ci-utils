from dataclasses import dataclass


@dataclass
class FakeClock:
    now: float = 100.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
