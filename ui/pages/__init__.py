# ui/pages/__init__.py
from .main_page import MainPage
from .login_page import TechnicianLoginPage
from .technician_page import TechnicianPage
from .recipe_pages import RecipeMenuPage, CreateRecipePage
from .edit_flow_page import EditFlowPage
from .deep_learning_page import DeepLearningPage

__all__ = [
    'MainPage',
    'TechnicianLoginPage',
    'TechnicianPage',
    'RecipeMenuPage',
    'CreateRecipePage',
    'EditFlowPage',
    'DeepLearningPage'
]