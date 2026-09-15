from django.db import models


class CarePlan(models.Model):
    patient_name = models.CharField(max_length=255)
    patient_dob = models.CharField(max_length=50)
    mrn = models.CharField(max_length=50)
    weight = models.CharField(max_length=50, blank=True)
    allergies = models.CharField(max_length=255, blank=True)
    primary_diagnosis = models.CharField(max_length=255, blank=True)
    drug_name = models.CharField(max_length=255)
    home_meds = models.CharField(max_length=500, blank=True)
    patient_records = models.TextField(blank=True)
    provider_name = models.CharField(max_length=255)
    npi = models.CharField(max_length=50)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.patient_name} - {self.drug_name}"
