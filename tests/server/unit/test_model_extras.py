"""Smaller model pieces not exercised by the lifecycle tests: IC highlights and P&ID
documents, isolation items, approval display strings, and PTW setters."""

from types import SimpleNamespace

from models.Isolation import IC, Isolation
from models.PTW import PTW
from models.User import UserRoles, UserDepartments, SecuredUser, User
from GlobalData import globalData
from utils import objToDict, dictToObj
from ptw_factory import make_ic, make_ptw, approval


class TestPidDocuments:
    def test_highlights_accept_dicts_namespaces_and_objects(self):
        h_obj = IC.Highlight(tag='XV-1', page=2, rect=[0.1, 0.2, 0.3, 0.4], state='close')
        doc = IC.PidWiringDocument(filename='p.pdf', original_filename='orig.pdf', page_count=3, ocr_used=True,
                                   highlights=[h_obj, {'tag': 'XV-2', 'page': 0}, SimpleNamespace(tag='XV-3', page=1, rect=[0, 0, 1, 1], state='open', manual=True)])
        assert [h.tag for h in doc.highlights] == ['XV-1', 'XV-2', 'XV-3']
        assert doc.highlights[0] is h_obj
        assert doc.highlights[1].rect == [0.0, 0.0, 0.0, 0.0] and doc.highlights[1].manual is False
        assert doc.highlights[2].manual is True

    def test_document_round_trips_through_db_shapes(self):
        doc = IC.PidWiringDocument(filename='p.pdf', page_count=2, highlights=[{'tag': 'T', 'page': 1, 'rect': [0.5, 0.5, 0.1, 0.1], 'state': 'open'}])
        as_row = dictToObj(objToDict(doc))
        back = IC.PidWiringDocument().setAll(namespace=as_row)
        assert isinstance(back.highlights[0], IC.Highlight) and back.highlights[0].rect == [0.5, 0.5, 0.1, 0.1]
        back2 = IC.PidWiringDocument().setAll(objToDict(doc))
        assert back2.highlights[0].tag == 'T' and back2.page_count == 2

    def test_ic_rebuilds_nested_documents(self):
        ic = make_ic(pid_documents=[{'filename': 'a.pdf', 'highlights': [{'tag': 'XV-1'}]}])
        assert isinstance(ic.pid_documents[0], IC.PidWiringDocument)
        assert isinstance(ic.pid_documents[0].highlights[0], IC.Highlight)
        clone = IC().setAll(namespace=dictToObj(objToDict(ic)))
        assert clone.pid_documents[0].highlights[0].tag == 'XV-1'


class TestIsolationItems:
    def test_item_defaults_and_setters(self):
        item = IC.IsolationItem(tag='XV-1', description='Inlet', state=IC.IsolationItem.States.CLOSE)
        assert (item.lock_num, item.lock_box_num) == ('', '')
        assert item.setLockNum('L1').setLockBoxNum('B1') is item
        assert (item.lock_num, item.lock_box_num) == ('L1', 'B1')
        assert [s.value for s in IC.IsolationItem.States] == ['open', 'close']

    def test_declarative_isolation_str(self):
        iso = Isolation(type=Isolation.Types.MECHANICAL, tag='XV-1', description='Inlet valve')
        assert str(iso) == 'Mechanical - Inlet valve XV-1'
        assert str(Isolation(type='Other', tag='T')) == 'Other -  T'
        assert Isolation().setAll({'tag': 'Z', 'bogus': 1}).tag == 'Z'
        assert Isolation().setAll(namespace=SimpleNamespace(tag='N')).tag == 'N'


class TestApprovalDisplay:
    def setup_method(self):
        self._saved = globalData.allUsers
        globalData.allUsers = {
            'coord': SecuredUser(username='coord', name='Cora', role=UserRoles.COORDINATOR, department=UserDepartments.PROD),
            'user_mech': SecuredUser(username='user_mech', name='Mike', role=UserRoles.USER, department=UserDepartments.MECH),
        }

    def teardown_method(self):
        globalData.allUsers = self._saved

    def test_ptw_approval_str(self):
        a = PTW.Approval(**approval(UserRoles.COORDINATOR, UserDepartments.PROD, username='coord'))
        assert str(a) == f'Approved by Coordinator Cora at {a.timestamp}'
        u = PTW.Approval(**approval(UserRoles.USER, UserDepartments.MECH, username='user_mech'))
        assert str(u) == f'Approved by User Mike (Mech) at {u.timestamp}'
        gone = PTW.Approval(**approval(UserRoles.PGM, UserDepartments.PROD, username='ghost'))
        assert str(gone) == f'Approved by [deleted user: ghost] at {gone.timestamp}'

    def test_ic_approval_role_dept_fallback(self):
        rec = IC.Approval(action='Approved', username='coord')
        assert rec.roleDept() == (UserRoles.COORDINATOR, UserDepartments.PROD)
        assert IC.Approval(action='Approved', username='ghost').roleDept() == (None, None)
        snap = IC.Approval(action='Approved', username='ghost', role='DFGM', department='IT')
        assert snap.roleDept() == ('DFGM', 'IT')

    def test_approver_matching_and_str(self):
        slot = PTW.Approver(UserRoles.USER, UserDepartments.MECH)
        assert slot.matchesUser(globalData.allUsers['user_mech']) is True
        assert slot.matchesUser(globalData.allUsers['coord']) is False
        assert slot.matchesUser(None) is False
        assert str(slot) == 'Mech' and str(PTW.Approver(UserRoles.DFGM)) == 'DFGM' and str(PTW.Approver(UserRoles.USER)) == 'User'
        assert PTW.Approver(UserRoles.DFGM) == PTW.Approver(UserRoles.DFGM) and hash(slot) == hash(PTW.Approver(UserRoles.USER, UserDepartments.MECH))
        assert slot != 'Mech'


class TestPtwSetters:
    def test_chainable_setters_and_list_helpers(self):
        ptw = (make_ptw().setId(5).setType(PTW.Types.HT).setLocation('Scarab').setEquipment('K-1').setAreaClass(PTW.AreaClasses.NHZ)
               .setDepartment('Mech').setDescription('d').setDate('01/01/2026 00:00:00').setRequestor('u').setMiwi('M').setMos(None).setFastTrack(True))
        assert (ptw.id, ptw.type, ptw.location, ptw.equipment, ptw.area_class) == (5, PTW.Types.HT, 'Scarab', 'K-1', PTW.AreaClasses.NHZ)
        assert (ptw.department, ptw.description, ptw.request_date, ptw.requestor, ptw.miwi, ptw.mos, ptw.fast_track) == ('Mech', 'd', '01/01/2026 00:00:00', 'u', 'M', None, True)
        ptw.addTool('Camera').addTool('Camera').addHazard('Noise').addHazard('Noise').addControl('Radios').addControl('Radios').addRisk('R').addRisk('R')
        assert ptw.tools.count('Camera') == 1 and ptw.hazards.count('Noise') == 1 and ptw.controls.count('Radios') == 1 and ptw.risks == ['R']
        ptw.removeTool('Camera').removeTool('Camera').removeHazard('Noise').removeControl('Radios').removeControl('nope')
        assert 'Camera' not in ptw.tools and 'Noise' not in ptw.hazards and 'Radios' not in ptw.controls
        ptw.addIsolation(Isolation(type='Mechanical', tag='XV-1'))
        assert ptw.isolations[-1].tag == 'XV-1'
        assert str(ptw).startswith('PTW #5 (Hot) - Mech - u - Scarab - Non-Hazardous - K-1')

    def test_user_model_accessors(self):
        u = User(username='a', password='p', name='A', role=UserRoles.USER, department='Mech', email='a@x')
        u.setTheme('dark').setLanguage('ar') if hasattr(u.setTheme('dark'), 'setLanguage') else u.setLanguage('ar')
        u.setMustChangePassword(True)
        assert (u.getTheme(), u.getLanguage(), u.getMustChangePassword(), u.getPassword()) == ('dark', 'ar', True, 'p')
        s = SecuredUser().setAll({'username': 'b', 'role': 'Issuing', 'department': 'Prod', 'ext': '12', 'is_active': False, 'bogus': 1})
        assert (s.getUsername(), s.getRole(), s.getDepartment(), s.getExt(), s.getIsActive()) == ('b', 'Issuing', 'Prod', '12', False)
        assert not hasattr(s, 'bogus')
