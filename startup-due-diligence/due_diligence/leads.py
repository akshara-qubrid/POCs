from .workers import tam_worker, competition_worker, product_assessment_worker, financial_worker


class MarketLead:
    def analyze(self, market: str):
        tam = tam_worker(market)
        comp = competition_worker(market)
        return {"tam": tam, "competition": comp}


class ProductLead:
    def analyze(self, product: str):
        p = product_assessment_worker(product)
        return {"product": p}


class FinancialLead:
    def analyze(self, data: str):
        f = financial_worker(data)
        return {"financial": f}
