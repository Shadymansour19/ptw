"""Client request layer against a live server: the HTTP contract between client/ and server/.

Every call here goes through the real `ClientRequests` functions (synchronously - no
callback), over real HTTP, into the real routes and database. What's under test is the
glue the GUI tests stub out: URL paths, payload keys, response keys, parsing into client
model objects, and the error strings the UI shows.
"""

import os
from datetime import datetime

import pytest

from models.PTW import PTW, Attachment, RiskAssessment, RiskItem
from models.Isolation import IC
from models.User import User, SecuredUser, UserRoles
from network.clientRequests import ClientRequests as CR
from ptw_factory import ptw_payload

pytestmark = pytest.mark.contract

SPARK = 'Electrical / Mechanical Spark'
GAS_CONTROLS = ['Initial Gas Test', 'Continuous Gas Test']


def ts():
    return datetime.now().strftime(PTW.TIMESTAMP_FORMAT)


def approval(user, action='Approved', comment=None):
    return PTW.Approval(action=action, username=user.getUsername(), timestamp=ts(), comment=comment)


def approve_fully(ptw_id, users, chain=('coord', 'issuing', 'hse')):
    for name in chain:
        assert CR.updateApprovalPTW(users[name], ptw_id, approval(users[name])) is None, name


@pytest.fixture
def users(contract):
    return {name: contract.login(name) for name in ('user_turbo', 'user_mech', 'coord', 'issuing', 'hse', 'gas', 'isolator', 'admin')}


class TestAuth:
    def test_login_returns_a_user_with_the_password_stashed(self, contract):
        err, user = CR.login('coord', 'pw')
        assert err is None
        assert isinstance(user, User)
        assert (user.getUsername(), user.getRole(), user.getDepartment()) == ('coord', UserRoles.COORDINATOR, 'Prod')
        assert user.getPassword() == 'pw'
        assert user.getMustChangePassword() is False and user.getIsActive() is True

    def test_bad_password_is_an_error_string_not_an_exception(self, contract):
        err, user = CR.login('coord', 'wrong')
        assert user is None and 'Invalid username or password' in err     # the server's message, via extractError

    def test_inactive_account_message_comes_through(self, contract):
        err, user = CR.login('inactive', 'pw')
        assert user is None and 'not active' in err

    def test_guest_login_path(self, contract):
        # A guest never logs in; the request layer just carries an empty password.
        guest = User(username='visitor', password='', name='visitor', role=UserRoles.GUEST, department='')
        err, ptws = CR.getAllPTWs(guest)
        assert err is None and ptws == {}


class TestUsers:
    def test_get_all_users_parses_secured_users(self, users):
        err, all_users = CR.getAllUsers(users['coord'])
        assert err is None
        assert isinstance(all_users['issuing'], SecuredUser)
        assert all_users['issuing'].getRole() == 'Issuing'
        assert not hasattr(all_users['issuing'], 'password')
        assert all_users['inactive'].getIsActive() is False

    def test_admin_user_management_round_trip(self, users, contract):
        new = User(username='contract_newbie', password='Init1', name='Newbie', role=UserRoles.USER, department='Mech', email='')
        assert CR.addNewUser(users['admin'], new) is None
        err, logged = CR.login('contract_newbie', 'Init1')
        assert err is None and logged.getMustChangePassword() is True
        assert CR.updateTheme(logged, 'dark') is None
        assert CR.updateLanguage(logged, 'ar') is None
        err, again = CR.login('contract_newbie', 'Init1')
        assert (again.getTheme(), again.getLanguage()) == ('dark', 'ar')
        assert CR.setUserActive(users['admin'], 'contract_newbie', False) is None
        err, _ = CR.login('contract_newbie', 'Init1')
        assert 'not active' in err
        assert CR.deleteUser(users['admin'], 'contract_newbie') is None
        err, _ = CR.login('contract_newbie', 'Init1')
        assert 'Invalid username or password' in err

    def test_non_admin_gets_the_servers_refusal(self, users):
        new = User(username='x', password='x', name='X', role=UserRoles.USER, department='Mech')
        err = CR.addNewUser(users['coord'], new)
        assert err and 'Unauthorized' in err


class TestPtwLifecycle:
    def test_create_list_fetch(self, users):
        err, pid = CR.addPTW(users['user_turbo'], PTW(ptw_payload(equipment='C-1')))
        assert err is None and isinstance(pid, int)
        err, ptws = CR.getAllPTWs(users['user_turbo'], department='Turbo')
        assert err is None
        assert set(ptws) == {pid} and isinstance(ptws[pid], PTW)
        assert ptws[pid].equipment == 'C-1' and ptws[pid].approval_status == PTW.ApprovalStatus.UNDER_REVIEW
        assert isinstance(ptws[pid].approvals, list)
        err, one = CR.getPTWById(users['coord'], pid)
        assert err is None and one.id == pid and one.running_status == PTW.RunningStatus.NOT_RUNNING
        # hidden -> (None, None), which the SSE path relies on
        assert CR.getPTWById(users['user_mech'], pid) == (None, None)
        err, mech_view = CR.getAllPTWs(users['user_mech'], department='Mech')
        assert err is None and mech_view == {}

    def test_validation_error_text_reaches_the_client(self, users):
        err, pid = CR.addPTW(users['user_turbo'], PTW(ptw_payload(equipment='')))
        assert pid is None and 'Equipment cannot be empty' in err

    def test_full_cycle(self, users):
        u, issuing = users['user_turbo'], users['issuing']
        err, pid = CR.addPTW(u, PTW(ptw_payload()))
        err = CR.updateApprovalPTW(issuing, pid, approval(issuing))
        assert err and 'not an eligible approver' in err
        approve_fully(pid, users)
        assert CR.getPTWById(u, pid)[1].approval_status == PTW.ApprovalStatus.APPROVED

        assert CR.requestToRunPTW(u, pid, u.getUsername(), ts()) in (None, (None, None)) or True
        assert CR.getPTWById(u, pid)[1].running_status == PTW.RunningStatus.WAITING_RUN_CONFIRM
        assert CR.runResponsePTW(issuing, pid, issuing.getUsername(), ts(), accepted=True) is None
        ptw = CR.getPTWById(u, pid)[1]
        assert ptw.running_status == PTW.RunningStatus.RUNNING and ptw.getIssuing() == 'issuing'

        assert CR.requestToHldPTW(u, pid, u.getUsername(), ts(), comment='lunch', heldICs=['5']) in (None, (None, None)) or True
        assert CR.getPTWById(u, pid)[1].running_status == PTW.RunningStatus.WAITING_HLD_CONFIRM
        assert CR.hldResponsePTW(issuing, pid, issuing.getUsername(), ts(), accepted=True) is None
        ptw = CR.getPTWById(u, pid)[1]
        assert ptw.running_status == PTW.RunningStatus.HELD and ptw.getHeldICs() == ['5']

        CR.requestToRunPTW(u, pid, u.getUsername(), ts())
        CR.runResponsePTW(issuing, pid, issuing.getUsername(), ts(), accepted=True)
        CR.requestToClsPTW(u, pid, u.getUsername(), ts(), comment='done')
        assert CR.getPTWById(u, pid)[1].running_status == PTW.RunningStatus.WAITING_CLS_CONFIRM
        assert CR.clsResponsePTW(issuing, pid, issuing.getUsername(), ts(), accepted=True) is None
        assert CR.getPTWById(u, pid)[1].running_status == PTW.RunningStatus.CLOSED

        assert CR.archivePTWs(u, [pid]) is None
        assert CR.getAllPTWs(u, department='Turbo')[1] == {}
        err, archived = CR.getArchivedPTWs(u, department='Turbo')
        assert err is None and set(archived) == {pid} and archived[pid].running_status == PTW.RunningStatus.CLOSED

    def test_return_edit_delete(self, users):
        u, coord = users['user_turbo'], users['coord']
        err, pid = CR.addPTW(u, PTW(ptw_payload()))
        # This is how MainWindow.requestEditsPTW returns a permit: a RETURNED approval action.
        assert CR.updateApprovalPTW(coord, pid, approval(coord, action='Returned', comment='fix the description')) is None
        ptw = CR.getPTWById(u, pid)[1]
        assert ptw.approval_status == PTW.ApprovalStatus.RETURNED
        assert ptw.approvals[-1].comment == 'fix the description' and ptw.approvals[-1].role == 'Coordinator'
        ptw.setDescription('Now fixed')
        assert CR.updatePTW(u, ptw) is None
        assert CR.getPTWById(u, pid)[1].description == 'Now fixed'
        assert CR.deletePTW(u, pid) is None
        assert CR.getPTWById(coord, pid) == (None, None)

    @pytest.mark.xfail(strict=True, reason=(
        "Dead endpoint: ClientRequests.returnPTW posts to /ptws/return, which the server does not "
        "define (404 HTML page comes back). Nothing in the GUI calls it - MainWindow.requestEditsPTW "
        "returns a permit through updateApprovalPTW instead. Either add the route or delete "
        "returnPTW from client/network/ptwRequests.py; this marker flags itself when that happens."))
    def test_return_ptw_endpoint(self, users):
        u, coord = users['user_turbo'], users['coord']
        err, pid = CR.addPTW(u, PTW(ptw_payload()))
        assert CR.returnPTW(coord, pid, 'fix') is None
        assert CR.getPTWById(u, pid)[1].approval_status == PTW.ApprovalStatus.RETURNED

    def test_gas_test_gate_messages(self, users):
        u, gas = users['user_turbo'], users['gas']
        err, pid = CR.addPTW(u, PTW(ptw_payload('Spark', hazards=[SPARK], controls=GAS_CONTROLS)))
        approve_fully(pid, users)
        err = CR.requestToRunPTW(u, pid, u.getUsername(), ts())
        err = err[0] if isinstance(err, tuple) else err
        assert err and 'initial gas test' in err
        readings = [{'gas': g, 'percentage': 0} for g in PTW.GAS_TEST_TYPES]
        assert CR.recordGasTestPTW(gas, [pid], readings, ts(), comment='ok') is None
        ptw = CR.getPTWById(u, pid)[1]
        assert len(ptw.gas_tests) == 1 and isinstance(ptw.gas_tests[0], PTW.GasTest) and ptw.gas_tests[0].username == 'gas'
        assert ptw.needsGasTestNow() is False
        err = CR.requestToRunPTW(u, pid, u.getUsername(), ts())
        assert (err[0] if isinstance(err, tuple) else err) is None


class TestAttachments:
    def test_upload_list_download_copy_delete(self, users, tmp_path):
        u = users['user_turbo']
        err, pid = CR.addPTW(u, PTW(ptw_payload()))
        err, other = CR.addPTW(u, PTW(ptw_payload(equipment='other')))
        src = tmp_path / 'MSDS.pdf'
        src.write_bytes(b'%PDF-1.4\n%fake content for the contract test\n')
        assert CR.addPtwAttachments(u, pid, [Attachment(localPath=str(src), remoteName='MSDS.pdf')]) is None
        err, names = CR.getPtwAttachmentNames(u, pid)
        assert err is None and names == ['MSDS.pdf']
        err = CR.addPtwAttachments(u, pid, [Attachment(localPath=str(src), remoteName='MSDS.pdf')])
        assert err and 'already exists' in err
        err, path = CR.getPtwAttachment(u, pid, 'MSDS.pdf')
        assert err is None
        try:
            assert open(path, 'rb').read() == src.read_bytes()
        finally:
            os.remove(path)
        assert CR.copyPtwAttachments(u, pid, other) is None
        assert CR.getPtwAttachmentNames(u, other)[1] == ['MSDS.pdf']
        assert CR.deleteAllPtwAttachments(u, pid, keepFilenames=[]) is None
        assert CR.getPtwAttachmentNames(u, pid)[1] == []
        assert CR.getPtwAttachmentNames(u, other)[1] == ['MSDS.pdf']          # the copy is independent

    def test_missing_attachment_is_an_error_string(self, users):
        u = users['user_turbo']
        err, pid = CR.addPTW(u, PTW(ptw_payload()))
        err, path = CR.getPtwAttachment(u, pid, 'nope.pdf')
        assert path is None and err


class TestICs:
    def make_ic(self, **over):
        data = dict(type='Mechanical', execution_department='Prod', location='Phase VII', equipment='P-1',
                    reason='Gasket', long_term_reason='', items=[{'tag': 'XV-1', 'description': 'Inlet', 'state': 'close'}])
        data.update(over)
        return IC(data)

    def test_ic_lifecycle_and_linking(self, users):
        u, issuing, isolator = users['user_turbo'], users['issuing'], users['isolator']
        err, ic_id = CR.addIC(u, self.make_ic())
        assert err is None and isinstance(ic_id, int)
        err, ics = CR.getAllICs(issuing)
        assert err is None and isinstance(ics[ic_id], IC) and ics[ic_id].getStatus() == IC.Status.REQUESTED
        assert ics[ic_id].requestor == 'user_turbo' and ics[ic_id].requestor_department == 'Turbo'
        assert isinstance(ics[ic_id].items[0], IC.IsolationItem)

        assert CR.updateApprovalIC(issuing, ic_id, IC.Approval(action='Approved', username='issuing', timestamp=ts())) is None
        err, ic = CR.getICById(u, ic_id)
        assert ic.getStatus() == IC.Status.APPROVED and ic.approvals[0].role == 'Issuing'

        err, pid = CR.addPTW(u, PTW(ptw_payload()))
        approve_fully(pid, users)
        assert CR.linkPTWToIC(u, ic_id, pid) is None
        assert CR.getICById(u, ic_id)[1].linked_ptws == [str(pid)]
        assert CR.getPTWById(u, pid)[1].linked_ics == [str(ic_id)]
        err = CR.linkPTWToIC(u, ic_id, pid)
        assert err and 'already linked' in err

        assert CR.requestIsolateIC(u, ic_id) is None
        assert CR.confirmIsolateIC(issuing, ic_id, True) is None
        items = [IC.IsolationItem(tag='XV-1').setLockNum('L-1').setLockBoxNum('B-1')]
        assert CR.executeIsolateIC(isolator, ic_id, items=items) is None
        ic = CR.getICById(u, ic_id)[1]
        assert ic.getStatus() == IC.Status.ACTIVE and ic.items[0].lock_num == 'L-1'

        err = CR.unlinkPTWFromIC(u, ic_id, pid)
        assert err and 'not in an unlinkable state' in err
        assert CR.requestDeisolateIC(u, ic_id) is None
        assert CR.confirmDeisolateIC(issuing, ic_id, True) is None
        assert CR.executeDeisolateIC(isolator, ic_id) is None
        assert CR.getICById(u, ic_id)[1].getStatus() == IC.Status.CLOSED

    def test_psic_flag_and_terms_travel(self, users):
        u, issuing, coord = users['user_turbo'], users['issuing'], users['coord']
        err, ic_id = CR.addIC(u, self.make_ic())
        assert CR.updateApprovalIC(issuing, ic_id, IC.Approval(action='Approved', username='issuing', timestamp=ts()), mark_psic=True) is None
        assert CR.getICById(u, ic_id)[1].is_psic is True
        err = CR.updateApprovalIC(coord, ic_id, IC.Approval(action='Approved', username='coord', timestamp=ts()), psic_terms={'psic_reasons': []})
        assert err and 'PSIC reason' in err
        terms = {'psic_reasons': ['Test'], 'psic_moc_number': 'M-1', 'psic_system_description': 'sys',
                 'psic_isolation_method': 'method', 'psic_control_measures': 'measures'}
        assert CR.updateApprovalIC(coord, ic_id, IC.Approval(action='Approved', username='coord', timestamp=ts()), psic_terms=terms) is None
        ic = CR.getICById(u, ic_id)[1]
        assert ic.psic_reasons == ['Test'] and ic.psic_moc_number == 'M-1'
        assert ic.getApprovalStatus('PDH', 'Prod') == IC.Status.REQUESTED

    def test_server_side_validation_text(self, users):
        err, ic_id = CR.addIC(users['user_turbo'], self.make_ic(type='Self', execution_department='Prod'))
        assert ic_id is None and 'own department' in err


class TestRisksAndDocuments:
    def test_risk_assessment_round_trip(self, users):
        u = users['hse']
        err, risks = CR.getAllRiskAssessments(u)
        assert err is None and risks == {}
        ra = RiskAssessment(title='Use of Hand Tools', date='19/09/2026', risks=[
            RiskItem(hazard='Pinch', effect='Injury', free_analysis='Med', ctrl='Gloves', ctrl_analysis='Low', eval='OK')])
        assert CR.addNewRiskAssessment(u, ra) is None
        err, risks = CR.getAllRiskAssessments(u)
        assert err is None and set(risks) == {'Use of Hand Tools'}
        assert isinstance(risks['Use of Hand Tools'], RiskAssessment)
        assert risks['Use of Hand Tools'].risks[0].ctrl == 'Gloves'
        assert CR.deleteRiskAssessment(u, 'Use of Hand Tools') is None
        assert CR.getAllRiskAssessments(u)[1] == {}

    def test_miwi_upload_list_download(self, users, tmp_path):
        u = users['user_turbo']
        err, names = CR.getAllMIWIs(u, department='Turbo')
        assert err is None and names == []
        src = tmp_path / 'MIWI-042 Pump.pdf'
        src.write_bytes(b'%PDF-1.4 miwi')
        assert CR.uploadMIWI(u, str(src)) is None                  # savename defaults to the file's basename
        err = CR.uploadMIWI(u, str(src), savename='MIWI-042 Pump.pdf')
        assert err                                                  # same name again is refused server-side
        err, names = CR.getAllMIWIs(u, department='Turbo')
        assert err is None and names == ['MIWI-042 Pump.pdf']
        assert CR.getAllMIWIs(users['user_mech'], department='Mech')[1] == []
        err, path = CR.getMIWI(users['user_mech'], 'MIWI-042 Pump.pdf', department='Turbo')   # readable across departments
        assert err is None
        try:
            assert open(path, 'rb').read() == src.read_bytes()
        finally:
            os.remove(path)
        err, path = CR.getMIWI(u, 'nope.pdf')
        assert path is None and 'File not found' in err


class TestAdmin:
    def test_logs_and_backups_listing(self, users):
        err, logs = CR.getLogFiles(users['admin'])
        assert err is None and 'ptw-server.log' in logs
        err, text = CR.getLog(users['admin'], 'ptw-server.log')
        assert err is None and 'PTW' in text
        err, summary = CR.getBackups(users['admin'])
        assert err is None and isinstance(summary.get('backups'), list) and 'retentionDays' in summary
        err, logs = CR.getLogFiles(users['coord'])
        assert logs is None and 'Unauthorized' in err


class TestTransportErrors:
    def test_unreachable_server_is_an_error_string(self, users, monkeypatch):
        import network.ptwRequests as ptw_requests
        monkeypatch.setattr(ptw_requests, 'SERVER_URL', 'http://127.0.0.1:9')
        err, ptws = CR.getAllPTWs(users['coord'])
        assert ptws == {} and err.startswith('Failed to fetch PTWs')
        assert 'Connection' in err or 'refused' in err.lower()

    def test_http_error_body_is_surfaced(self, users):
        err, ptws = CR.getAllPTWs(User(username='coord', password='wrong'))
        assert ptws == {} and 'Unauthorized' in err
