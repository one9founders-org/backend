import pytest

from api.management.commands.purge_gpt_store import list_gpt_store_rows
from tests.factories import ToolFactory


@pytest.mark.django_db
def test_lists_only_chatgpt_store_urls():
    ToolFactory(name="Figma", website="https://figma.com")
    ToolFactory(name="Expert Economist", website="https://chat.openai.com/g/g-abc")
    ToolFactory(name="Other GPT", website="https://chatgpt.com/g/g-xyz")

    names = {row["name"] for row in list_gpt_store_rows()}

    assert names == {"Expert Economist", "Other GPT"}
