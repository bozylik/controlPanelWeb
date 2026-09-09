from .connection import ConnectionMixin, MSK
from .users import UsersMixin
from .schedule import ScheduleMixin
from .cancels import CancelsMixin
from .exemptions import ExemptionsMixin
from .checkins import CheckinsMixin  # ← обязательно есть
from .summary import SummaryMixin


class Database(
    ConnectionMixin,
    UsersMixin,
    ScheduleMixin,
    CancelsMixin,
    ExemptionsMixin,
    CheckinsMixin,     # ← обязательно есть
    SummaryMixin,
):
    """Единая точка доступа к базе данных"""
    pass


db = Database()