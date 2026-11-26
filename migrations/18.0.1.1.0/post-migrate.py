"""18.0.1.1.0: the contract sequence is shared by all companies.

The sequence is `noupdate` data, so existing databases keep the company it
was created with; contracts of other companies then got no number."""


def migrate(cr, version):
    cr.execute("UPDATE ir_sequence SET company_id = NULL WHERE code = 'car.rental.sequence'")
