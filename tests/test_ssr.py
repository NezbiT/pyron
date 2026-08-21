import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from pyron import Form, Pyron, redirect
from pyron.cli import app as cli

runner = CliRunner()


@pytest.mark.asyncio
async def test_html_form_and_flash(tmp_path):
    (tmp_path / "hi.html").write_text(
        "{% if flash %}<p class='flash'>{{ flash.text }}</p>{% endif %}"
        "<form method='post'><input name='title'/></form>",
        encoding="utf-8",
    )
    app = Pyron(title="ssr", templates=str(tmp_path), docs_url=None, redoc_url=None)

    @app.get("/")
    async def home(request):
        return await app.render(request, "hi.html")

    @app.post("/")
    async def add(title: str = Form()):
        return redirect("/", message=f"Added {title}.")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.post("/", data={})
        assert missing.status_code == 422
        posted = await client.post("/", data={"title": "Copper"}, follow_redirects=True)
        assert posted.status_code == 200
        assert "Added Copper." in posted.text


def test_init_ssr_is_one_model_html_and_api(tmp_path):
    dest = tmp_path / "shop"
    result = runner.invoke(cli, ["init", str(dest), "--template", "ssr"])
    assert result.exit_code == 0, result.output
    main = (dest / "app" / "main.py").read_text(encoding="utf-8")
    assert "Form" in main
    assert "redirect" in main
    assert "_ITEMS" not in main
    index = (dest / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'name="title"' in index
    assert "Add item" in index
    css = (dest / "static" / "style.css").read_text(encoding="utf-8")
    assert "#c2410c" in css
    assert "Georgia" not in css
