"""
PHANTOM Stealth Layer
Fingerprinting, human behavior simulation, and WebDriver evasion.
"""

from phantom.stealth.evasion import EvasionScripts
from phantom.stealth.fingerprint import BrowserFingerprint, FingerprintGenerator
from phantom.stealth.humanizer import HumanBehaviorSimulator

__all__ = [
    "BrowserFingerprint",
    "FingerprintGenerator",
    "HumanBehaviorSimulator",
    "EvasionScripts",
]
