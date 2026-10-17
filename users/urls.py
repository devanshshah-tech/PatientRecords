from django.urls import path
from . import views

urlpatterns = [
    path('health/', views.health, name='health'),
    path('', views.index, name='index'),
    path('access-denied/', views.access_denied, name='access_denied'),
    path('submit-patient-details/', views.submit_patient_details, name='submit_patient_details'),
    path('doctor/compare/', views.comparison, name='comparison'),
    path('doctor/', views.doctor_search, name='doctor_search'),
    path('photos/<uuid:photo_id>/', views.private_photo, name='private_photo'),
]
