"""
PHANTOM DOM Extractor
CSS/XPath selector-based data extraction, JavaScript injection,
and table parsing from live Playwright pages.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

from loguru import logger


class DOMExtractor:
    """
    Extracts structured data from a Playwright page using CSS selectors,
    XPath expressions, and JavaScript evaluation.
    """

    def __init__(self, page: Any) -> None:
        self._page = page

    async def extract_by_selectors(
        self,
        selectors: Dict[str, str],
        multiple: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, Union[str, List[str], None]]:
        """
        Extract data fields using CSS selectors.

        Args:
            selectors: Mapping of field_name -> CSS selector
            multiple: Mapping of field_name -> True if we want all matches

        Returns:
            Dict of field_name -> extracted text (or list if multiple=True)
        """
        if multiple is None:
            multiple = {}

        results: Dict[str, Union[str, List[str], None]] = {}

        for field_name, selector in selectors.items():
            want_all = multiple.get(field_name, False)
            try:
                if want_all:
                    elements = await self._page.query_selector_all(selector)
                    texts = []
                    for el in elements:
                        text = await el.inner_text()
                        if text and text.strip():
                            texts.append(text.strip())
                    results[field_name] = texts
                else:
                    element = await self._page.query_selector(selector)
                    if element:
                        text = await element.inner_text()
                        results[field_name] = text.strip() if text else None
                    else:
                        results[field_name] = None
            except Exception as exc:
                logger.warning("Selector extraction failed for '{}': {}", field_name, exc)
                results[field_name] = None

        return results

    async def extract_attribute(
        self,
        selector: str,
        attribute: str,
    ) -> Optional[str]:
        """Extract a specific attribute from the first matching element."""
        try:
            element = await self._page.query_selector(selector)
            if element:
                return await element.get_attribute(attribute)
        except Exception as exc:
            logger.warning("Attribute extraction failed: {}", exc)
        return None

    async def extract_all_attributes(
        self,
        selector: str,
        attribute: str,
    ) -> List[str]:
        """Extract an attribute from all matching elements."""
        try:
            elements = await self._page.query_selector_all(selector)
            results = []
            for el in elements:
                val = await el.get_attribute(attribute)
                if val:
                    results.append(val)
            return results
        except Exception as exc:
            logger.warning("Bulk attribute extraction failed: {}", exc)
            return []

    async def extract_html(self, selector: str) -> Optional[str]:
        """Extract innerHTML from the first matching element."""
        try:
            element = await self._page.query_selector(selector)
            if element:
                return await element.inner_html()
        except Exception as exc:
            logger.debug("HTML extraction failed: {}", exc)
        return None

    async def extract_table(self, selector: str = "table") -> List[Dict[str, str]]:
        """
        Parse an HTML table into a list of row dicts.

        Args:
            selector: CSS selector for the <table> element

        Returns:
            List of dicts where keys are column headers.
        """
        try:
            table_data: Any = await self._page.evaluate(
                f"""
                () => {{
                    const table = document.querySelector('{selector}');
                    if (!table) return null;

                    const headers = Array.from(table.querySelectorAll('thead th, thead td'))
                        .map(th => th.innerText.trim());

                    if (headers.length === 0) {{
                        // No thead — use first row as headers
                        const firstRow = table.querySelector('tr');
                        if (firstRow) {{
                            headers.push(...Array.from(firstRow.querySelectorAll('th, td'))
                                .map(td => td.innerText.trim()));
                        }}
                    }}

                    const rows = Array.from(table.querySelectorAll('tbody tr, tr:not(:first-child)'));
                    return rows.map(row => {{
                        const cells = Array.from(row.querySelectorAll('td, th'))
                            .map(td => td.innerText.trim());
                        const obj = {{}};
                        cells.forEach((cell, i) => {{
                            obj[headers[i] || `col_${{i}}`] = cell;
                        }});
                        return obj;
                    }});
                }}
                """
            )
            if table_data and isinstance(table_data, list):
                return [dict(row) for row in table_data]
        except Exception as exc:
            logger.warning("Table extraction failed: {}", exc)
        return []

    async def extract_json_from_page(self, variable_name: str) -> Optional[Any]:
        """
        Extract a JavaScript variable or expression from the page.

        Args:
            variable_name: JS expression to evaluate (e.g. 'window.__DATA__')

        Returns:
            Parsed Python object or None.
        """
        try:
            result = await self._page.evaluate(f"() => {variable_name}")
            return result
        except Exception as exc:
            logger.debug("JS variable extraction '{}' failed: {}", variable_name, exc)
        return None

    async def extract_meta_tags(self) -> Dict[str, str]:
        """Extract all <meta> tag name/content pairs."""
        try:
            meta_data: Any = await self._page.evaluate(
                """
                () => {
                    const metas = {};
                    document.querySelectorAll('meta[name], meta[property]').forEach(m => {
                        const key = m.getAttribute('name') || m.getAttribute('property');
                        const val = m.getAttribute('content');
                        if (key && val) metas[key] = val;
                    });
                    return metas;
                }
                """
            )
            return dict(meta_data) if meta_data else {}
        except Exception as exc:
            logger.debug("Meta tag extraction failed: {}", exc)
            return {}

    async def extract_json_ld_scripts(self) -> List[Dict[str, Any]]:
        """Extract all JSON-LD <script type="application/ld+json"> blocks."""
        try:
            raw_scripts: Any = await self._page.evaluate(
                """
                () => Array.from(
                    document.querySelectorAll('script[type="application/ld+json"]')
                ).map(s => s.textContent)
                """
            )
            results = []
            for script_text in (raw_scripts or []):
                try:
                    parsed = json.loads(script_text)
                    if isinstance(parsed, list):
                        results.extend(parsed)
                    else:
                        results.append(parsed)
                except json.JSONDecodeError:
                    pass
            return results
        except Exception as exc:
            logger.debug("JSON-LD extraction failed: {}", exc)
            return []

    async def wait_and_extract(
        self,
        selector: str,
        timeout_ms: int = 10_000,
    ) -> Optional[str]:
        """Wait for a selector to appear, then extract its text."""
        try:
            await self._page.wait_for_selector(selector, timeout=timeout_ms)
            element = await self._page.query_selector(selector)
            if element:
                text = await element.inner_text()
                return text.strip() if text else None
        except Exception as exc:
            logger.debug("Wait-and-extract '{}' failed: {}", selector, exc)
        return None
