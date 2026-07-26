"""Tests for resume version management (core/resume/version_manager.py)."""

from core.resume.schema import ResumeData, Skill, WorkExperience
from core.resume.version_manager import VersionManager


def _resume() -> ResumeData:
    return ResumeData(
        work_experience=[WorkExperience(company="Acme", position="Dev")],
        skills=[Skill(name="Python")],
    )


class TestVersionManager:
    def test_create_and_list(self, tmp_path):
        vm = VersionManager(storage_dir=tmp_path)
        v = vm.create_version(_resume(), name="master")
        listed = vm.list_versions()
        assert len(listed) == 1
        assert listed[0]["id"] == v.id

    def test_persistence_roundtrip(self, tmp_path):
        vm = VersionManager(storage_dir=tmp_path)
        v = vm.create_version(_resume(), name="master")
        vm2 = VersionManager(storage_dir=tmp_path)
        loaded = vm2.get_version(v.id)
        assert loaded.name == "master"
        assert loaded.resume_data.work_experience[0].company == "Acme"

    def test_fork_is_independent(self, tmp_path):
        vm = VersionManager(storage_dir=tmp_path)
        base = vm.create_version(_resume(), name="base")
        fork = vm.fork_version(base.id, "tailored")
        fork.resume_data.work_experience[0].company = "Changed"
        assert vm.get_version(base.id).resume_data.work_experience[0].company == "Acme"

    def test_diff_modified_field(self, tmp_path):
        vm = VersionManager(storage_dir=tmp_path)
        base = vm.create_version(_resume(), name="base")
        fork = vm.fork_version(base.id, "tailored")
        fork.resume_data.work_experience[0].position = "Senior Dev"
        vm.update_version(fork.id, fork.resume_data)

        diff = vm.diff_versions(base.id, fork.id)
        modified = [d for d in diff.diffs if d.diff_type == "modified"]
        assert len(modified) == 1
        assert "position" in modified[0].changed_fields

    def test_diff_skill_added(self, tmp_path):
        vm = VersionManager(storage_dir=tmp_path)
        base = vm.create_version(_resume(), name="base")
        fork = vm.fork_version(base.id, "tailored")
        fork.resume_data.skills.append(Skill(name="Go"))
        vm.update_version(fork.id, fork.resume_data)

        diff = vm.diff_versions(base.id, fork.id)
        added = [d for d in diff.diffs if d.section == "skills" and d.diff_type == "added"]
        assert added and added[0].new_entry["skills"][0]["name"] == "Go"

    def test_delete_clears_child_parent_link(self, tmp_path):
        vm = VersionManager(storage_dir=tmp_path)
        base = vm.create_version(_resume(), name="base")
        fork = vm.fork_version(base.id, "child")
        assert vm.delete_version(base.id)
        assert vm.get_version(fork.id).parent_id is None
