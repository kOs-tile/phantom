"""
PHANTOM WebDriver Evasion Scripts
JavaScript injection payloads and CDP commands to hide automation fingerprints.
Overrides navigator.webdriver, fakes navigator.plugins, spoofs chrome.runtime.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger


class EvasionScripts:
    """
    Collection of JavaScript evasion scripts for bypassing anti-bot detection.

    All scripts are designed to be injected via Playwright's
    `page.add_init_script()` or `page.evaluate()` to run before
    page scripts detect automation.
    """

    @staticmethod
    def hide_webdriver() -> str:
        """
        Override navigator.webdriver to return undefined.
        This is the most commonly checked automation flag.
        """
        return """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
        """

    @staticmethod
    def fake_chrome_runtime() -> str:
        """
        Spoof window.chrome.runtime to mimic a real Chrome extension environment.
        Headless Chrome lacks chrome.runtime which is a major detection vector.
        """
        return """
        if (!window.chrome) {
            window.chrome = {};
        }
        if (!window.chrome.runtime) {
            window.chrome.runtime = {
                id: undefined,
                connect: function() {},
                sendMessage: function() {},
                onMessage: { addListener: function() {} },
                onConnect: { addListener: function() {} },
                getManifest: function() { return {}; },
                getURL: function(path) { return 'chrome-extension://invalid/' + path; },
                reload: function() {}
            };
        }
        """

    @staticmethod
    def fake_navigator_plugins(count: int = 5) -> str:
        """
        Spoof navigator.plugins with realistic plugin entries.
        An empty plugins array is a strong headless indicator.
        """
        return f"""
        const _plugins = [
            {{
                name: 'Chrome PDF Plugin',
                description: 'Portable Document Format',
                filename: 'internal-pdf-viewer',
                length: 1,
                item: function(i) {{ return this[i]; }},
                namedItem: function(n) {{ return this[n]; }},
                0: {{type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: null}}
            }},
            {{
                name: 'Chrome PDF Viewer',
                description: '',
                filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                length: 1,
                item: function(i) {{ return this[i]; }},
                namedItem: function(n) {{ return this[n]; }},
                0: {{type: 'application/pdf', suffixes: 'pdf', description: '', enabledPlugin: null}}
            }},
            {{
                name: 'Native Client',
                description: '',
                filename: 'internal-nacl-plugin',
                length: 2,
                item: function(i) {{ return this[i]; }},
                namedItem: function(n) {{ return this[n]; }},
                0: {{type: 'application/x-nacl', suffixes: '', description: 'Native Client Executable', enabledPlugin: null}},
                1: {{type: 'application/x-pnacl', suffixes: '', description: 'Portable Native Client Executable', enabledPlugin: null}}
            }}
        ];

        Object.defineProperty(navigator, 'plugins', {{
            get: function() {{
                const pluginArray = Object.create(PluginArray.prototype);
                Object.defineProperty(pluginArray, 'length', {{ get: () => _plugins.length }});
                _plugins.forEach((p, i) => {{
                    pluginArray[i] = p;
                }});
                pluginArray.item = function(i) {{ return this[i]; }};
                pluginArray.namedItem = function(n) {{
                    for (let p of _plugins) {{
                        if (p.name === n) return p;
                    }}
                    return null;
                }};
                pluginArray.refresh = function() {{}};
                return pluginArray;
            }},
            configurable: true
        }});
        """

    @staticmethod
    def fake_mime_types() -> str:
        """Spoof navigator.mimeTypes to match a real browser."""
        return """
        const _mimeTypes = [
            { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: null },
            { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: null },
            { type: 'application/x-nacl', suffixes: '', description: 'Native Client Executable', enabledPlugin: null },
            { type: 'application/x-pnacl', suffixes: '', description: 'Portable Native Client Executable', enabledPlugin: null }
        ];

        Object.defineProperty(navigator, 'mimeTypes', {
            get: function() {
                const mimeArray = Object.create(MimeTypeArray.prototype);
                Object.defineProperty(mimeArray, 'length', { get: () => _mimeTypes.length });
                _mimeTypes.forEach((m, i) => { mimeArray[i] = m; });
                mimeArray.item = function(i) { return this[i]; };
                mimeArray.namedItem = function(n) {
                    for (let m of _mimeTypes) {
                        if (m.type === n) return m;
                    }
                    return null;
                };
                return mimeArray;
            },
            configurable: true
        });
        """

    @staticmethod
    def override_permissions_query() -> str:
        """
        Override Permissions.query to prevent fingerprinting via permission state checks.
        Bots often return 'denied' for notifications; real users return 'prompt'.
        """
        return """
        const _originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : _originalQuery(parameters)
        );
        """

    @staticmethod
    def spoof_languages(languages: Optional[List[str]] = None) -> str:
        """Override navigator.languages to match configured locale."""
        if languages is None:
            languages = ["en-US", "en"]
        langs_json = str(languages).replace("'", '"')
        return f"""
        Object.defineProperty(navigator, 'languages', {{
            get: () => {langs_json},
            configurable: true
        }});
        """

    @staticmethod
    def disable_automation_controlled() -> str:
        """Remove the 'AutomationControlled' feature from navigator userAgentData."""
        return """
        if (navigator.userAgentData) {
            Object.defineProperty(navigator.userAgentData, 'brands', {
                get: () => [
                    { brand: 'Google Chrome', version: '124' },
                    { brand: 'Not-A.Brand', version: '99' },
                    { brand: 'Chromium', version: '124' }
                ],
                configurable: true
            });
        }
        """

    @staticmethod
    def fix_iframe_contentwindow() -> str:
        """
        Fix iframe.contentWindow.navigator.webdriver detection bypass.
        Some anti-bot checks inspect iframes separately.
        """
        return """
        const _iframeProto = HTMLIFrameElement.prototype;
        const _origContentWindow = Object.getOwnPropertyDescriptor(_iframeProto, 'contentWindow');
        if (_origContentWindow) {
            Object.defineProperty(_iframeProto, 'contentWindow', {
                get: function() {
                    const win = _origContentWindow.get.call(this);
                    if (win) {
                        try {
                            Object.defineProperty(win.navigator, 'webdriver', {
                                get: () => undefined,
                                configurable: true
                            });
                        } catch(e) {}
                    }
                    return win;
                },
                configurable: true
            });
        }
        """

    @staticmethod
    def spoof_hardware_concurrency(cores: int = 8) -> str:
        """Override navigator.hardwareConcurrency (CPU cores)."""
        return f"""
        Object.defineProperty(navigator, 'hardwareConcurrency', {{
            get: () => {cores},
            configurable: true
        }});
        """

    @staticmethod
    def spoof_device_memory(gb: int = 8) -> str:
        """Override navigator.deviceMemory."""
        return f"""
        Object.defineProperty(navigator, 'deviceMemory', {{
            get: () => {gb},
            configurable: true
        }});
        """

    @classmethod
    def get_full_evasion_script(
        cls,
        languages: Optional[List[str]] = None,
        hardware_concurrency: int = 8,
        device_memory: int = 8,
    ) -> str:
        """
        Compile the complete evasion script bundle.
        Inject this once via page.add_init_script() per context.

        Returns:
            Single concatenated JavaScript string with all evasion overrides.
        """
        scripts = [
            cls.hide_webdriver(),
            cls.fake_chrome_runtime(),
            cls.fake_navigator_plugins(),
            cls.fake_mime_types(),
            cls.override_permissions_query(),
            cls.spoof_languages(languages),
            cls.disable_automation_controlled(),
            cls.fix_iframe_contentwindow(),
            cls.spoof_hardware_concurrency(hardware_concurrency),
            cls.spoof_device_memory(device_memory),
        ]
        return "\n;\n".join(scripts)

    @staticmethod
    def get_cdp_args() -> List[str]:
        """
        Chromium launch arguments that reduce automation detection.

        Returns:
            List of --flag strings to pass to browser launch.
        """
        return [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-zygote",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-ipc-flooding-protection",
            "--disable-hang-monitor",
            "--disable-prompt-on-repost",
            "--disable-sync",
            "--metrics-recording-only",
            "--safebrowsing-disable-auto-update",
            "--password-store=basic",
            "--use-mock-keychain",
            "--lang=en-US",
        ]

    @staticmethod
    def get_ignore_default_args() -> List[str]:
        """Arguments to exclude from Playwright's default Chrome launch args."""
        return [
            "--enable-automation",
            "--enable-blink-features=IdleDetection",
        ]
