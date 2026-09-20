from typing import Protocol

from .internet import ReadUrlSkill, WebSearchSkill


class Skill(Protocol):
    name: str

    def run(self, payload: dict) -> dict:
        ...


class SkillRegistry:
    def __init__(self):
        self.skills: dict[str, Skill] = {
            "read_url": ReadUrlSkill(),
            "web_search": WebSearchSkill(),
        }

    def skill_names(self) -> list[str]:
        return sorted(self.skills)

    def get(self, name: str) -> Skill:
        skill = self.skills.get(name)
        if not skill:
            raise ValueError(f"Skill is not registered: {name}")
        return skill

    def run(self, name: str, payload: dict) -> dict:
        return self.get(name).run(payload)
