from pathlib import Path

from ccgram.msg_skill import (
    SKILL_CONTENT,
    SKILL_DIR_NAME,
    SKILL_FILE_NAME,
    _skill_path,
    ensure_skill_installed,
    install_skill,
)


class TestSkillFileGeneration:
    def test_skill_content_has_frontmatter(self):
        assert SKILL_CONTENT.startswith("---\n")
        assert "name: ccgram-messaging" in SKILL_CONTENT
        assert "description:" in SKILL_CONTENT

    def test_skill_content_has_register_instructions(self):
        assert "ccgram msg register" in SKILL_CONTENT
        assert "--task" in SKILL_CONTENT
        assert "--team" in SKILL_CONTENT

    def test_skill_content_has_inbox_check(self):
        assert "ccgram msg inbox" in SKILL_CONTENT

    def test_skill_content_has_send_instructions(self):
        assert "ccgram msg send" in SKILL_CONTENT
        assert "--wait" in SKILL_CONTENT

    def test_skill_content_has_broadcast_instructions(self):
        assert "ccgram msg broadcast" in SKILL_CONTENT

    def test_skill_content_has_spawn_instructions(self):
        assert "ccgram msg spawn" in SKILL_CONTENT

    def test_skill_content_requires_user_consent(self):
        assert "summarize" in SKILL_CONTENT.lower()
        assert "ask before processing" in SKILL_CONTENT.lower()

    def test_skill_content_auto_spawn_exception(self):
        assert "--auto" in SKILL_CONTENT
        assert "process messages immediately" in SKILL_CONTENT.lower()

    def test_skill_content_has_reply_instructions(self):
        assert "ccgram msg reply" in SKILL_CONTENT

    def test_skill_content_has_find_instructions(self):
        assert "ccgram msg find" in SKILL_CONTENT
        assert "ccgram msg list-peers" in SKILL_CONTENT


class TestSkillInstallation:
    def test_installs_to_correct_path(self, tmp_path: Path):
        install_skill(tmp_path)
        expected = tmp_path / ".claude" / "skills" / SKILL_DIR_NAME / SKILL_FILE_NAME
        assert expected.exists()
        assert expected.read_text() == SKILL_CONTENT

    def test_creates_parent_directories(self, tmp_path: Path):
        install_skill(tmp_path)
        skill_dir = tmp_path / ".claude" / "skills" / SKILL_DIR_NAME
        assert skill_dir.is_dir()

    def test_idempotent_same_content(self, tmp_path: Path):
        assert install_skill(tmp_path) is True
        assert install_skill(tmp_path) is False

    def test_updates_outdated_content(self, tmp_path: Path):
        install_skill(tmp_path)
        skill_path = _skill_path(tmp_path)
        skill_path.write_text("old content")
        assert install_skill(tmp_path) is True
        assert skill_path.read_text() == SKILL_CONTENT

    def test_returns_true_on_fresh_install(self, tmp_path: Path):
        assert install_skill(tmp_path) is True

    def test_returns_false_when_unchanged(self, tmp_path: Path):
        install_skill(tmp_path)
        assert install_skill(tmp_path) is False


class TestEnsureSkillInstalled:
    def test_installs_when_missing(self, tmp_path: Path):
        assert ensure_skill_installed(tmp_path) is True
        assert _skill_path(tmp_path).exists()

    def test_skips_when_current(self, tmp_path: Path):
        install_skill(tmp_path)
        assert ensure_skill_installed(tmp_path) is False

    def test_updates_when_outdated(self, tmp_path: Path):
        install_skill(tmp_path)
        _skill_path(tmp_path).write_text("stale")
        assert ensure_skill_installed(tmp_path) is True

    def test_returns_false_for_nonexistent_cwd(self, tmp_path: Path):
        fake = tmp_path / "does-not-exist"
        assert ensure_skill_installed(fake) is False

    def test_accepts_string_path(self, tmp_path: Path):
        assert ensure_skill_installed(str(tmp_path)) is True
        assert _skill_path(tmp_path).exists()
