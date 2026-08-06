from network.authRequests import AuthRequests
from network.userRequests import UserRequests
from network.ptwRequests import PTWRequests
from network.icRequests import ICRequests
from network.riskRequests import RiskRequests
from network.documentRequests import DocumentRequests
from network.adminRequests import AdminRequests


class ClientRequests(AuthRequests, UserRequests, PTWRequests, ICRequests, RiskRequests, DocumentRequests, AdminRequests):
    pass
