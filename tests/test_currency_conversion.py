import sys
import types

# Provide a minimal flask stub if Flask is not available
if 'flask' not in sys.modules:
    flask_stub = types.ModuleType('flask')
    flask_stub.session = {}
    sys.modules['flask'] = flask_stub

from app.utils import portfolio_utils


def test_update_prices_conversion(monkeypatch):
    companies = [{'id': 1, 'name': 'TestCo', 'identifier': 'TEST'}]

    def fake_get_isin_data(identifier):
        return {'success': True, 'price': 10.0, 'currency': 'USD'}

    def fake_get_exchange_rate(from_currency, to_currency='EUR'):
        assert from_currency == 'USD'
        return 0.5

    monkeypatch.setattr(portfolio_utils, 'get_isin_data', fake_get_isin_data)
    monkeypatch.setattr(portfolio_utils, 'get_exchange_rate', fake_get_exchange_rate)

    result = portfolio_utils.update_prices(companies, 1)
    assert result[0]['price_eur'] == 5.0
    assert result[0]['currency'] == 'USD'
