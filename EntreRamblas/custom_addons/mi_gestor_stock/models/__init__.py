from . import mgs_config
from . import mgs_backup
from . import res_company
from . import product_template
from . import mgs_stock_lot
from . import mgs_pos_stock
from . import mgs_scrap
from . import mgs_stock_alert
from . import mgs_reception
from . import mgs_monthly_report
from . import mgs_security
from . import mgs_hardware_job
from . import mgs_pos_session
from . import mgs_inventory_count
from . import mgs_damaged_return
from . import mgs_opening_stock
from . import mgs_catalog_import
# mgs_bouquet DESPUES de mgs_pos_stock: los dos heredan
# stock.picking._create_move_from_pos_order_lines y se reparten las lineas del
# ticket sin pisarse (uno se queda las composiciones, el otro el resto) solo
# porque Odoo antepone en el MRO la clase importada mas tarde. Si esto se
# reordena, un test lo nota (ver test_bouquet.py,
# test_a_ticket_with_a_bouquet_and_a_loose_product_moves_both).
from . import mgs_bouquet
from . import mgs_event
from . import mgs_purchase
from . import mgs_purchase_forecast
from . import mgs_pricelist_campaign
from . import mgs_consumption
from . import mgs_expiry
