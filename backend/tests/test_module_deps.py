"""scripts/check_module_deps.py must flag what the module rules forbid, not just pass everything."""

import importlib.util
from pathlib import Path

script = Path(__file__).resolve().parents[2] / "scripts" / "check_module_deps.py"
spec = importlib.util.spec_from_file_location("check_module_deps", script)
deps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deps)


def test_backend_rules():
    assert deps.backend_violations("core", "core/x.py", "from equipment.models import Equipment")  # upward
    assert deps.backend_violations("knowledge", "knowledge/x.py", "from datasets.views import x")  # not in table
    assert deps.backend_violations("system", "system/x.py", "from accounts.member_views import X")  # private
    assert deps.backend_violations("workbench", "workbench/x.py", "def f():\n    from reports.views import x")
    assert not deps.backend_violations("research", "research/x.py", "from datasets.versions import pin_versions")
    assert not deps.backend_violations("workbench", "workbench/x.py", "from procurement.queries import x\nimport django")


def test_frontend_rules():
    page = "modules/equipment/views/EquipmentDetailView.vue"
    assert not deps.frontend_violations(page, "import { docsApi } from '@/modules/knowledge/api'")
    assert deps.frontend_violations(page, "import X from '@/modules/knowledge/views/KnowledgeView.vue'")
    assert deps.frontend_violations(page, "import X from '../../knowledge/components/DocDialog.vue'")
    assert not deps.frontend_violations(page, "import X from '../components/EquipmentFormDialog.vue'")
    assert deps.frontend_violations("components/StatusTag.vue", "import { x } from '@/modules/equipment/api'")
    assert not deps.frontend_violations("router/index.ts", "import equipment from '@/modules/equipment'")
    legacy = "views/ExperimentEditView.vue"  # not moved into a module yet
    assert not deps.frontend_violations(legacy, "import { equipmentApi } from '@/modules/equipment/api'")
    assert deps.frontend_violations(legacy, "import X from '@/modules/equipment/components/EquipmentFormDialog.vue'")


def test_current_code_follows_the_rules(capsys):
    assert deps.main() == 0, capsys.readouterr().out
