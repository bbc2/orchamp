from bs4 import BeautifulSoup
from inline_snapshot import snapshot

from orchamp_get.html_transform import _anonymize_soup, _soup_to_html, _strip_soup


def _strip_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    _strip_soup(soup)
    return _soup_to_html(soup)


def _anonymize_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    _anonymize_soup(soup)
    return str(soup)


class TestStripHtml:
    def test_removes_head_metadata(self) -> None:
        html = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8" />
<title>Test</title>
<meta name="viewport" content="width=device-width" />
<link rel="stylesheet" href="style.css" />
</head>
<body><p>Content</p></body>
</html>"""

        result = _strip_html(html)

        assert result == snapshot(
            """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta content="width=device-width" name="viewport"/>
</head>
<body><p>Content</p></body>
</html>"""
        )

    def test_removes_nav_header_footer(self) -> None:
        html = """<html>
<body>
<nav><a href="/">Home</a></nav>
<header><h1>Title</h1></header>
<main><p>Content</p></main>
<footer><p>Footer</p></footer>
</body>
</html>"""

        result = _strip_html(html)

        assert result == snapshot(
            """\
<html>
<body>
<main><p>Content</p></main>
</body>
</html>"""
        )

    def test_preserves_form_elements(self) -> None:
        html = """<html>
<body>
<form><table><tr><td>Data</td></tr></table></form>
</body>
</html>"""

        result = _strip_html(html)

        assert result == snapshot(
            """\
<html>
<body>
<form><table><tr><td>Data</td></tr></table></form>
</body>
</html>"""
        )

    def test_removes_tfoot_elements(self) -> None:
        html = """<html>
<body>
<table>
<thead><tr><th>Header</th></tr></thead>
<tfoot><tr><td>Footer</td></tr></tfoot>
<tbody><tr><td>Data</td></tr></tbody>
</table>
</body>
</html>"""

        result = _strip_html(html)

        assert result == snapshot(
            """\
<html>
<body>
<table>
<thead><tr><th>Header</th></tr></thead>
<tbody><tr><td>Data</td></tr></tbody>
</table>
</body>
</html>"""
        )

    def test_removes_noprint_elements(self) -> None:
        html = """<html>
<body>
<table>
<tr>
<td class="noprint"><input type="radio" /></td>
<td class="club">Team A</td>
</tr>
</table>
</body>
</html>"""

        result = _strip_html(html)

        assert result == snapshot(
            """\
<html>
<body>
<table>
<tr>
<td class="club">Team A</td>
</tr>
</table>
</body>
</html>"""
        )

    def test_removes_span_access_elements(self) -> None:
        html = """<html>
<body>
<th>P<span class="access">oin</span>ts</th>
</body>
</html>"""

        result = _strip_html(html)

        assert result == snapshot(
            """\
<html>
<body>
<th>Pts</th>
</body>
</html>"""
        )

    def test_preserves_labels(self) -> None:
        html = """<html>
<body>
<td class="club"><label for="team_a">Team A</label></td>
</body>
</html>"""

        result = _strip_html(html)

        assert result == snapshot(
            """\
<html>
<body>
<td class="club"><label for="team_a">Team A</label></td>
</body>
</html>"""
        )


class TestAnonymizeHtml:
    def test_anonymizes_team_ids_and_names(self) -> None:
        html = """<html>
<body>
<table class="tablesorter">
<tbody>
<tr><td class="club acme_ping"><label for="acme_ping">ACME Ping</label></td></tr>
<tr><td class="club sf_tt"><label for="sf_tt">SF TT</label></td></tr>
</tbody>
</table>
</body>
</html>"""

        result = _anonymize_html(html)

        assert result == snapshot("""\
<html>
<body>
<table class="tablesorter">
<tbody>
<tr><td class="club team_a"><label for="team_a">Team A</label></td></tr>
<tr><td class="club team_b"><label for="team_b">Team B</label></td></tr>
</tbody>
</table>
</body>
</html>\
""")

    def test_anonymizes_match_table_references(self) -> None:
        html = """<html>
<body>
<table class="tablesorter">
<tbody>
<tr><td class="club alpha"><label for="alpha">Alpha</label></td></tr>
<tr><td class="club beta"><label for="beta">Beta</label></td></tr>
</tbody>
</table>
<table class="champ">
<tbody>
<tr>
<td class="club alpha"><label for="alpha">Alpha</label></td>
<td>10</td>
<td>8</td>
<td class="club beta"><label for="beta">Beta</label></td>
</tr>
</tbody>
</table>
</body>
</html>"""

        result = _anonymize_html(html)

        assert result == snapshot(
            """\
<html>
<body>
<table class="tablesorter">
<tbody>
<tr><td class="club team_a"><label for="team_a">Team A</label></td></tr>
<tr><td class="club team_b"><label for="team_b">Team B</label></td></tr>
</tbody>
</table>
<table class="champ">
<tbody>
<tr>
<td class="club team_a"><label for="team_a">Team A</label></td>
<td>10</td>
<td>8</td>
<td class="club team_b"><label for="team_b">Team B</label></td>
</tr>
</tbody>
</table>
</body>
</html>"""
        )
