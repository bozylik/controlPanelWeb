"""Единая точка доступа к базе данных"""
from .connection import ConnectionMixin, MSK
from .users import UsersMixin
from .schedule import ScheduleMixin
from .cancels import CancelsMixin
from .exemptions import ExemptionsMixin
from .checkins import CheckinsMixin
from .summary import SummaryMixin


class Database(
    ConnectionMixin,
    UsersMixin,
    ScheduleMixin,
    CancelsMixin,
    ExemptionsMixin,
    CheckinsMixin,
    SummaryMixin,
):
    """Единая точка доступа к базе данных"""
    pass


db = Database()