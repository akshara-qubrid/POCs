from .tools import tam_analysis, competition_analysis, product_assessment, revenue_model, unit_economics, funding_risk


class MarketLead:
    def analyze(self, market: str):
        tam = tam_analysis(market)
        comp = competition_analysis(market)
        return {"tam": tam, "competition": comp}


class ProductLead:
    def analyze(self, product: str):
        p = product_assessment(product)
        return {"product": p}


class FinancialLead:
    def analyze(self, data: str):
        rev = revenue_model(data)
        ue = unit_economics(data)
        fr = funding_risk(data)
        return {"revenue_model": rev, "unit_economics": ue, "funding_risk": fr}
