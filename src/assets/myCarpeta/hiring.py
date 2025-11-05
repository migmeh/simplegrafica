import uuid
from datetime import datetime, timedelta

from sqlite3 import IntegrityError

import redis
from sqlalchemy import text
from sqlalchemy.orm import joinedload, contains_eager
import re

from src.messages.general import USER_EXIST
from src.models.response import response, response_error
from src.db.dao import Beneficiaries, CostAbsence, LoanHistory, LoanManagement, db, CategoriesUser, Users, Hires, DocumentChecklists, EmployementHistory, \
    FichaTecnica, EmailNotificationsNewContracts
from src.util.methods import today_wh_h, age_calculate



CURP_PATTERN = re.compile(r"^[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]{2}$") 
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)


def _to_bool(value):
    """Normaliza distintos inputs a booleano.

    - bool -> permanece igual
    - None -> False
    - strings 'true','1','si','sí','yes' -> True
    - numeric-like -> bool(int(value))
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "si", "sí", "y", "yes")
    try:
        return bool(int(value))
    except Exception:
        return False


def create_new_hiring(data):
    try:
        required_fields = ['first_name', 'first_last_name', 'second_last_name']
        for field in required_fields:
            if not data.get(field):
                return response_error(f"{field} is required", 400)

        is_rehire = data.get('is_rehire', False)
        if is_rehire:
            user = Users.query.get_or_404(data.get('id_user'))
            if user.is_active:
                return response_error({'data': "User is already active", 'status': False}, 401)

        else:
            valid_user = Users.query.filter_by(
                first_name=data.get('first_name'), 
                last_name=data.get('first_last_name'),
                second_name=data.get('second_name'), 
                second_last_name=data.get('second_last_name')
            ).first()

            if valid_user:
                return response_error({'data': USER_EXIST, 'status': False}, 401)

        is_active_user = data.get('status') == 'Contratado'
        created_at = today_wh_h() if is_active_user else None
        id_external = generate_id_external() if is_active_user else None

        new_user = Users(
            uid=uuid.uuid4(),
            first_name=data.get('first_name'),
            second_name=data.get('second_name'),
            last_name=data.get('first_last_name'),
            second_last_name=data.get('second_last_name'),
            email=data.get('email'),
            cellphone=data.get('phone_number'),
            birthday=data.get('birth_date'),
            is_active=is_active_user,
            created_at=created_at,
            id_category=data.get('position'),
            type_operation_supervisor=0,
            id_grip_external=id_external
        )
        db.session.add(new_user)
        db.session.flush()

        new_hire = Hires(
            id_user=new_user.id,
            status_hire=data.get('status'),
            gender=data.get('gender'),
            nationality=data.get('nationality'),
            marital_status=data.get('marital_status'),
            address=data.get('address'),
            postal_code=data.get('postal_code'),
            curp=data.get('curp'),
            rfc=data.get('rfc'),
            nss=data.get('nss'),
            infonavit=data.get('infonavit'),
            fonacot=data.get('fonacot'),
            capacitation_date=data.get('training_date'),
            observation_capacitation=data.get('trainer_observation'),
            diary_salary=data.get('integrated_daily_salary'),
            bank=data.get('bank'),
            bank_account=data.get('interbank_key'),
            blood_type=data.get('blood_type'),
            dopping = data.get('dopping'),
            cartilla=data.get('card'),
            personal_in_charge=data.get('staff_in_charge'),
            experience=data.get('experience'),
            recluter_id=data.get('recruiter'),
            service_id=data.get('service'),
            shift_id=data.get('turno'),
            education_level=data.get('educationLevel'),
            first_job=data.get('firstJob'),
            service_attitude=data.get('actitudServicio'),
            adherence_to_rules=data.get('apegoNormas'),
            judgment=data.get('juicio'),
            teamwork=data.get('trabajoEquipo'),
            is_rehire=is_rehire,
        )
        db.session.add(new_hire)
        db.session.flush()

        db.session.add(
            FichaTecnica(
                cellphone=data.get('phone_number'),
                type_blood=data.get('blood_type'),
                age=age_calculate(data.get('birth_date')),
                civil_status=data.get('marital_status').upper() if data.get('marital_status') else None,
                id_user=new_user.id
            )
        )        


        if len(data.get('beneficiaries', [])) > 0:
            for ben in data.get('beneficiaries'):
                try:
                    percentage = float(ben.get('percentage')) if ben.get('percentage') is not None else None
                except (ValueError, TypeError):
                    percentage = None  

                new_beneficiary = Beneficiaries(
                    id_hire=new_hire.id,
                    full_name=ben.get('beneficiary_name'),
                    relationship=ben.get('relationship'),
                    percentage_benefit=percentage
                )
                db.session.add(new_beneficiary)


        if len(data.get('jobs', [])) > 0:
            for job in data.get('jobs'):
                new_job = EmployementHistory(
                    id_hire=new_hire.id,
                    company_name=job.get('nameJob'),
                    company_period=job.get('period'),
                    zone=job.get('zoneJob'),
                    schedule=job.get('schedule'),
                    last_salary=job.get('lastSalary'),
                    observation=job.get('observations'),
                    motive_leave=job.get('reasonForResignation'),
                )
                db.session.add(new_job)

        if data.get('documentos'):
            for documento in data['documentos']:
                prorroga_val = _to_bool(documento.get('prorroga'))
                new_doc = DocumentChecklists(
                    id_hire=new_hire.id,
                    document_name=documento.get('nombre'),
                    status=False if documento.get('completo') is None else documento.get('completo'),
                    prorroga=prorroga_val
                )
                db.session.add(new_doc)

        db.session.commit()
        return response("Hiring created successfully", 200)

    except IntegrityError as ie:
        db.session.rollback()
        return response_error("Integrity error: " + str(ie), 500)
    except Exception as e:
        db.session.rollback()
        return response_error(str(e), 500)


def update_hirings(data):
    try:
        if not isinstance(data, list):
            return response_error("Data must be a list", 400)

        required_fields = ['id', 'first_name', 'first_last_name', 'second_last_name', 'id_user']
        for record in data:
            for field in required_fields:
                if not record.get(field):
                    return response_error(f"{field} is required for record with id {record.get('id', 'unknown')}", 400)

        users_mappings = []
        hires_mappings = []

        id_max_external = generate_id_external()

        for record in data:
            user = Users.query.get(record.get('id_user'))
            was_hired_before = user.is_active if user else False

            user_mapping = {
                "id": record.get('id_user'),
                "first_name": record.get('first_name'),
                "second_name": record.get('second_name'),
                "last_name": record.get('first_last_name'),
                "second_last_name": record.get('second_last_name'),
                "email": record.get('email'),
                "cellphone": record.get('phone_number'),
                "birthday": record.get('birth_date'),
                "is_active": True if record.get('status') == 'Contratado' else False,
                "id_category": record.get('position'),
                "type_operation_supervisor": 0,
            }

            if not was_hired_before and user_mapping["is_active"]:
                user_mapping["created_at"] = today_wh_h()
                if user.id_grip_external is None:
                    user_mapping["id_grip_external"] = id_max_external
                    id_max_external = str(int(id_max_external) + 1)

            users_mappings.append(user_mapping)

            hire_mapping = {
                "id": record.get('id'),
                "status_hire": record.get('status'),
                "gender": record.get('gender'),
                "nationality": record.get('nationality'),
                "marital_status": record.get('marital_status'),
                "address": record.get('address'),
                "postal_code": record.get('postal_code'),
                "curp": record.get('curp'),
                "rfc": record.get('rfc'),
                "nss": record.get('nss'),
                "infonavit": record.get('infonavit'),
                "fonacot": record.get('fonacot'),
                "capacitation_date": record.get('training_date'),
                "diary_salary": record.get('integrated_daily_salary'),
                "bank": record.get('bank'),
                "bank_account": record.get('interbank_key'),
                "blood_type": record.get('blood_type'),
                "dopping": record.get('dopping'),
                "cartilla": record.get('card'),
                "personal_in_charge": record.get('staff_in_charge'),
                "experience": record.get('experience'),
                "recluter_id": record.get('recruiter'),
                "service_id": record.get('service'),
                "shift_id": record.get('turno'),
                "education_level": record.get('educationLevel'),
                "first_job": record.get('firstJob'),
                "service_attitude": record.get('actitudServicio'),
                "adherence_to_rules": record.get('apegoNormas'),
                "judgment": record.get('juicio'),
                "teamwork": record.get('trabajoEquipo'),
                "is_rehire": record.get('is_rehire', False),
            }

            hires_mappings.append(hire_mapping)

        db.session.bulk_update_mappings(Users, users_mappings)
        db.session.bulk_update_mappings(Hires, hires_mappings)
        db.session.commit()

        return response("Hirings updated successfully", 200)
    except Exception as e:
        db.session.rollback()
        return response_error(str(e), 500)


def update_a_hirings(data):
    try:
        required_fields = ['id', 'first_name', 'first_last_name', 'second_last_name', 'id_user']
        for field in required_fields:
            if not data.get(field):
                return response_error(f"{field} is required", 400)

        user = Users.query.get_or_404(data.get('id_user'))
        was_hired_before = user.is_active if user else False

        user.first_name = data.get('first_name')
        user.second_name = data.get('second_name')
        user.last_name = data.get('first_last_name')
        user.second_last_name = data.get('second_last_name')
        user.email = data.get('email')
        user.cellphone = data.get('phone_number')
        user.birthday = data.get('birth_date')
        if user.id_grip_external is None:
            print("User is not hired")
            user.is_active = True if data.get('status') == 'Contratado' else False
        user.id_category = data.get('position')
        user.created_at = data.get('entry_date')
        user.type_operation_supervisor = 0

        if not was_hired_before and user.is_active:
            user.created_at = today_wh_h()
            user.id_grip_external = generate_id_external() if user.id_grip_external is None else user.id_grip_external

        db.session.add(user)
        db.session.flush()

        hire = Hires.query.get_or_404(data.get('id'))
        hire.status_hire = data.get('status')
        hire.gender = data.get('gender')
        hire.nationality = data.get('nationality')
        hire.marital_status = data.get('marital_status')
        hire.address = data.get('address')
        hire.postal_code = data.get('postal_code')
        hire.curp = data.get('curp')
        hire.rfc = data.get('rfc')
        hire.nss = data.get('nss')
        hire.infonavit = data.get('infonavit')
        hire.fonacot = data.get('fonacot')
        hire.capacitation_date = data.get('training_date')
        hire.diary_salary = data.get('integrated_daily_salary')
        hire.bank = data.get('bank')
        hire.bank_account = data.get('interbank_key')
        hire.blood_type = data.get('blood_type')
        hire.dopping = data.get('dopping')
        hire.cartilla = data.get('card')
        hire.personal_in_charge = data.get('staff_in_charge')
        hire.experience = data.get('experience')
        hire.recluter_id = data.get('recruiter')
        hire.service_id = data.get('service')
        hire.shift_id = data.get('turno')
        hire.education_level = data.get('educationLevel')
        hire.first_job = data.get('firstJob')
        hire.service_attitude = data.get('actitudServicio')
        hire.adherence_to_rules = data.get('apegoNormas')
        hire.judgment = data.get('juicio')
        hire.teamwork = data.get('trabajoEquipo')
        hire.is_rehire = data.get('is_rehire', False) or False

        db.session.add(hire)

        beneficiaries_mappings = []
        if len(data.get('beneficiaries', [])) > 0:
            for ben in data.get('beneficiaries'):
                try:
                    percentage = float(ben.get('percentage')) if ben.get('percentage') is not None else None
                except (ValueError, TypeError):
                    percentage = None  

                beneficiary = Beneficiaries.query.get_or_404(ben.get('id'))
                mapping = {
                    "id": beneficiary.id,
                    "full_name": ben.get('beneficiary_name'),
                    "relationship": ben.get('relationship'),
                    "percentage_benefit": percentage
                }
                beneficiaries_mappings.append(mapping)

            db.session.bulk_update_mappings(Beneficiaries, beneficiaries_mappings)

        jobs_mappings = []
        if len(data.get('jobs', [])) > 0:
            for job_data in data.get('jobs'):
                job_obj = EmployementHistory.query.get_or_404(job_data.get('id'))
                mapping = {
                    "id": job_obj.id,
                    "company_name": job_data.get('nameJob'),
                    "company_period": job_data.get('period'),
                    "zone": job_data.get('zoneJob'),
                    "schedule": job_data.get('schedule'),
                    "last_salary": job_data.get('lastSalary'),
                    "observation": job_data.get('observations'),
                    "motive_leave": job_data.get('reasonForResignation')
                }
                jobs_mappings.append(mapping)

            db.session.bulk_update_mappings(EmployementHistory, jobs_mappings)



        existing_documents = {doc.document_name: doc for doc in DocumentChecklists.query.filter_by(id_hire=hire.id).all()}
        for doc_data in data.get('documentos', []):
            doc_name = doc_data.get('nombre')
            doc_status = doc_data.get('completo', False)
            prorroga_val = _to_bool(doc_data.get('prorroga'))

            if doc_name in existing_documents:
                existing_documents[doc_name].status = doc_status
                # actualizar también el campo prorroga si existe en la petición
                try:
                    existing_documents[doc_name].prorroga = prorroga_val
                except Exception:
                    # en caso de que el modelo no tenga el atributo, ignoramos
                    pass
            else:
                db.session.add(DocumentChecklists(id_hire=hire.id, document_name=doc_name, status=doc_status, prorroga=prorroga_val))


        db.session.commit()

        for key in redis_client.scan_iter("user_list:*"):
            redis_client.delete(key)

        return response("Hiring updated successfully", 200)

    except Exception as e:
        db.session.rollback()
        return response_error(str(e), 500)


def get_recent_hires_json(filter):
    try:
        valid_filters = ['Borrador', 'Contratado', 'Rechazado']
        if filter is not None and filter not in valid_filters:
            return response_error(f"Invalid filter value. Valid values are: {', '.join(valid_filters)}", 400)
        

        base_sql = """
            WITH filtered_hires AS (
                SELECT h.id, h.id_user, h.status_hire, h.gender, h.nationality, 
                       h.marital_status, h.address, h.postal_code, h.curp, h.rfc, 
                       h.nss, h.infonavit, h.fonacot, h.capacitation_date, 
                       h.observation_capacitation, h.diary_salary, h.bank, h.bank_account, 
                       h.blood_type, h.dopping, h.cartilla, h.personal_in_charge, 
                       h.experience, h.recluter_id, h.service_id, h.shift_id, 
                       h.education_level, h.first_job, h.service_attitude, 
                       h.adherence_to_rules, h.judgment, h.teamwork, h.created_at
                FROM hires h
                WHERE {where_condition}
                ORDER BY h.id DESC
            )
            SELECT json_agg(result) AS hires
            FROM (
                SELECT json_build_object(
                    'id', h.id,
                    'id_user', h.id_user,
                    'id_grip_external', u.id_grip_external,
                    'first_name', u.first_name,
                    'second_name', u.second_name,
                    'first_last_name', u.last_name,
                    'second_last_name', u.second_last_name,
                    'email', u.email,
                    'phone_number', u.cellphone,
                    'birth_date', u.birthday,
                    'position', u.id_category,
                    'status', h.status_hire,
                    'gender', h.gender,
                    'nationality', h.nationality,
                    'marital_status', h.marital_status,
                    'address', h.address,
                    'postal_code', h.postal_code,
                    'curp', h.curp,
                    'rfc', h.rfc,
                    'nss', h.nss,
                    'infonavit', h.infonavit,
                    'fonacot', h.fonacot,
                    'training_date', h.capacitation_date,
                    'trainer_observation', h.observation_capacitation,
                    'integrated_daily_salary', COALESCE(h.diary_salary, s.sdi),
                    'bank', h.bank,
                    'interbank_key', h.bank_account,
                    'blood_type', h.blood_type,
                    'dopping', h.dopping,
                    'card', h.cartilla,
                    'staff_in_charge', h.personal_in_charge,
                    'experience', h.experience,
                    'recruiter', h.recluter_id,
                    'service', h.service_id,
                    'turno', h.shift_id,
                    'is_active', u.is_active,
                    'lote_imss', u.lote_imss,
                    'entry_date', TO_CHAR(u.created_at, 'YYYY-MM-DD'),
                    'educationLevel', h.education_level,
                    'firstJob', h.first_job,
                    'actitudServicio', h.service_attitude,
                    'apegoNormas', h.adherence_to_rules,
                    'juicio', h.judgment,
                    'trabajoEquipo', h.teamwork,
                    'beneficiaries', COALESCE(beneficiaries_data.beneficiaries, '[]'),
                    'jobs', COALESCE(jobs_data.jobs, '[]'),
                    'documentos', COALESCE(docs_data.documentos, '[]')
                ) AS result
                FROM filtered_hires h
                JOIN users u ON h.id_user = u.id
                LEFT JOIN salaries s ON u.salary_id = s.id
                LEFT JOIN LATERAL (
                    SELECT json_agg(json_build_object(
                        'id', b.id,
                        'beneficiary_name', b.full_name,
                        'relationship', b.relationship,
                        'percentage', b.percentage_benefit
                    )) AS beneficiaries
                    FROM beneficiaries b
                    WHERE b.id_hire = h.id
                ) beneficiaries_data ON true
                LEFT JOIN LATERAL (
                    SELECT json_agg(json_build_object(
                        'id', e.id,
                        'nameJob', e.company_name,
                        'period', e.company_period,
                        'lastSalary', e.last_salary,
                        'zoneJob', e.zone,
                        'schedule', e.schedule,
                        'observations', e.observation,
                        'reasonForResignation', e.motive_leave
                    )) AS jobs
                    FROM employement_history e
                    WHERE e.id_hire = h.id
                ) jobs_data ON true
                LEFT JOIN LATERAL (
                    SELECT json_agg(
                        json_build_object(
                            'id', d.id,
                            'nombre', d.document_name,
                            'completo', d.status
                        ) ORDER BY d.id ASC
                    ) AS documentos
                    FROM document_checklists d
                    WHERE d.id_hire = h.id
                ) docs_data ON true
            ) sub;
        """

        if filter is None:
            where_condition = "h.created_at >= :filter_date"
            filter_value = datetime.utcnow() - timedelta(days=2)
        else:
            where_condition = "h.status_hire = :filter_status"
            filter_value = filter

        base_sql = base_sql.format(where_condition=where_condition)

        if filter is None:
            res = db.session.execute(
                text(base_sql), 
                {"filter_date": filter_value}
            ).fetchone()
        else:
            res = db.session.execute(
                text(base_sql), 
                {"filter_status": filter_value}
            ).fetchone()

        hires_data = res.hires if res.hires is not None else []
        return response(hires_data, 200)
        
    except Exception as e:
        return response_error(str(e), 500)


def get_recent_hires_paginated(filter, page=1, per_page=50):
    """
    Versión optimizada con paginación de get_recent_hires_json
    """
    try:
        valid_filters = ['Borrador', 'Contratado', 'Rechazado']
        if filter is not None and filter not in valid_filters:
            return response_error(f"Invalid filter value. Valid values are: {', '.join(valid_filters)}", 400)
        
        # Validar parámetros de paginación
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 50
            
        # Calcular offset
        offset = (page - 1) * per_page
        
        # Query optimizada con paginación
        base_sql = """
            WITH filtered_hires AS (
                SELECT h.id, h.id_user, h.status_hire, h.gender, h.nationality, 
                       h.marital_status, h.address, h.postal_code, h.curp, h.rfc, 
                       h.nss, h.infonavit, h.fonacot, h.capacitation_date, 
                       h.observation_capacitation, h.diary_salary, h.bank, h.bank_account, 
                       h.blood_type, h.dopping, h.cartilla, h.personal_in_charge, 
                       h.experience, h.recluter_id, h.service_id, h.shift_id, 
                       h.education_level, h.first_job, h.service_attitude, 
                       h.adherence_to_rules, h.judgment, h.teamwork, h.created_at
                FROM hires h
                WHERE {where_condition}
                ORDER BY h.id DESC
                LIMIT :limit OFFSET :offset
            )
            SELECT json_agg(result) AS hires
            FROM (
                SELECT json_build_object(
                    'id', h.id,
                    'id_user', h.id_user,
                    'id_grip_external', u.id_grip_external,
                    'first_name', u.first_name,
                    'second_name', u.second_name,
                    'first_last_name', u.last_name,
                    'second_last_name', u.second_last_name,
                    'email', u.email,
                    'phone_number', u.cellphone,
                    'birth_date', u.birthday,
                    'position', u.id_category,
                    'is_active', u.is_active,
                    'status', h.status_hire,
                    'gender', h.gender,
                    'nationality', h.nationality,
                    'marital_status', h.marital_status,
                    'address', h.address,
                    'postal_code', h.postal_code,
                    'curp', h.curp,
                    'rfc', h.rfc,
                    'nss', h.nss,
                    'infonavit', h.infonavit,
                    'fonacot', h.fonacot,
                    'training_date', h.capacitation_date,
                    'trainer_observation', h.observation_capacitation,
                    'integrated_daily_salary', COALESCE(h.diary_salary, s.sdi),
                    'bank', h.bank,
                    'interbank_key', h.bank_account,
                    'blood_type', h.blood_type,
                    'dopping', h.dopping,
                    'card', h.cartilla,
                    'staff_in_charge', h.personal_in_charge,
                    'experience', h.experience,
                    'recruiter', h.recluter_id,
                    'service', h.service_id,
                    'turno', h.shift_id,
                    'is_active', u.is_active,
                    'lote_imss', u.lote_imss,
                    'entry_date', TO_CHAR(u.created_at, 'YYYY-MM-DD'),
                    'educationLevel', h.education_level,
                    'firstJob', h.first_job,
                    'actitudServicio', h.service_attitude,
                    'apegoNormas', h.adherence_to_rules,
                    'juicio', h.judgment,
                    'trabajoEquipo', h.teamwork,
                    'beneficiaries', COALESCE(beneficiaries_data.beneficiaries, '[]'),
                    'jobs', COALESCE(jobs_data.jobs, '[]'),
                    'documentos', COALESCE(docs_data.documentos, '[]')
                ) AS result
                FROM filtered_hires h
                JOIN users u ON h.id_user = u.id
                LEFT JOIN salaries s ON u.salary_id = s.id
                LEFT JOIN LATERAL (
                    SELECT json_agg(json_build_object(
                        'id', b.id,
                        'beneficiary_name', b.full_name,
                        'relationship', b.relationship,
                        'percentage', b.percentage_benefit
                    )) AS beneficiaries
                    FROM beneficiaries b
                    WHERE b.id_hire = h.id
                ) beneficiaries_data ON true
                LEFT JOIN LATERAL (
                    SELECT json_agg(json_build_object(
                        'id', e.id,
                        'nameJob', e.company_name,
                        'period', e.company_period,
                        'lastSalary', e.last_salary,
                        'zoneJob', e.zone,
                        'schedule', e.schedule,
                        'observations', e.observation,
                        'reasonForResignation', e.motive_leave
                    )) AS jobs
                    FROM employement_history e
                    WHERE e.id_hire = h.id
                ) jobs_data ON true
                LEFT JOIN LATERAL (
                    SELECT json_agg(
                        json_build_object(
                            'id', d.id,
                            'nombre', d.document_name,
                            'completo', d.status
                        ) ORDER BY d.id ASC
                    ) AS documentos
                    FROM document_checklists d
                    WHERE d.id_hire = h.id
                ) docs_data ON true
            ) sub;
        """
        
        # Query para contar total de registros
        count_sql = """
            SELECT COUNT(*) as total
            FROM hires h
            WHERE {where_condition}
        """

        if filter is None:
            where_condition = "h.created_at >= :filter_date"
            filter_value = datetime.utcnow() - timedelta(days=2)
        else:
            where_condition = "h.status_hire = :filter_status"
            filter_value = filter

        base_sql = base_sql.format(where_condition=where_condition)
        count_sql = count_sql.format(where_condition=where_condition)

        # Ejecutar query de conteo
        if filter is None:
            count_result = db.session.execute(
                text(count_sql), 
                {"filter_date": filter_value}
            ).fetchone()
        else:
            count_result = db.session.execute(
                text(count_sql), 
                {"filter_status": filter_value}
            ).fetchone()

        total_records = count_result.total

        # Ejecutar query principal
        if filter is None:
            res = db.session.execute(
                text(base_sql), 
                {
                    "filter_date": filter_value,
                    "limit": per_page,
                    "offset": offset
                }
            ).fetchone()
        else:
            res = db.session.execute(
                text(base_sql), 
                {
                    "filter_status": filter_value,
                    "limit": per_page,
                    "offset": offset
                }
            ).fetchone()

        hires_data = res.hires if res.hires is not None else []
        
        # Calcular información de paginación
        total_pages = (total_records + per_page - 1) // per_page
        
        return response({
            'data': hires_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_records': total_records,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            }
        }, 200)
        
    except Exception as e:
        return response_error(str(e), 500)


def search_hires(search_term, filter_status):
    """
    Función de búsqueda
    Busca en: first_name, second_name, first_last_name, second_last_name, emp_no, id_grip_external, nss
    """
    try:
        if not search_term or len(search_term.strip()) < 2:
            return response_error("El término de búsqueda debe tener al menos 2 caracteres.", 400)
        
        valid_filters = ['Borrador', 'Contratado', 'Rechazado', 'Ultimos Creados']
        if filter_status is not None and filter_status not in valid_filters:
            return response_error(f"Filtro inválido. Valores válidos: {', '.join(valid_filters)}", 400)
        
        search_term = f"%{search_term.strip().lower()}%"

        if filter_status == 'Ultimos Creados':
            filter_value = datetime.utcnow() - timedelta(days=2)
            additional_filter = "AND h.created_at >= :filter_date"
        else:
            additional_filter = "AND h.status_hire = :filter_status"
        
        search_sql = """
            WITH search_results AS (
                SELECT DISTINCT h.id, h.id_user, h.status_hire, h.gender, h.nationality, 
                       h.marital_status, h.address, h.postal_code, h.curp, h.rfc, 
                       h.nss, h.infonavit, h.fonacot, h.capacitation_date, 
                       h.observation_capacitation, h.diary_salary, h.bank, h.bank_account, 
                       h.blood_type, h.dopping, h.cartilla, h.personal_in_charge, 
                       h.experience, h.recluter_id, h.service_id, h.shift_id, 
                       h.education_level, h.first_job, h.service_attitude, 
                       h.adherence_to_rules, h.judgment, h.teamwork, h.created_at
                FROM hires h
                JOIN users u ON h.id_user = u.id
                WHERE (LOWER(u.first_name) LIKE :search_term
                   OR LOWER(u.second_name) LIKE :search_term
                   OR LOWER(u.last_name) LIKE :search_term
                   OR LOWER(u.second_last_name) LIKE :search_term
                   OR LOWER(u.id::text) LIKE :search_term
                   OR CAST(u.id_grip_external AS TEXT) LIKE :search_term
                   OR LOWER(h.nss) LIKE :search_term)
                   {additional_filter}
                ORDER BY h.id DESC
                LIMIT 100 
            )
            SELECT json_agg(result) AS hires
            FROM (
                SELECT json_build_object(
                    'id', h.id,
                    'id_user', h.id_user,
                    'id_grip_external', u.id_grip_external,
                    'first_name', u.first_name,
                    'second_name', u.second_name,
                    'first_last_name', u.last_name,
                    'second_last_name', u.second_last_name,
                    'email', u.email,
                    'phone_number', u.cellphone,
                    'birth_date', u.birthday,
                    'position', u.id_category,
                    'status', h.status_hire,
                    'gender', h.gender,
                    'nationality', h.nationality,
                    'marital_status', h.marital_status,
                    'address', h.address,
                    'postal_code', h.postal_code,
                    'curp', h.curp,
                    'rfc', h.rfc,
                    'nss', h.nss,
                    'infonavit', h.infonavit,
                    'fonacot', h.fonacot,
                    'training_date', h.capacitation_date,
                    'trainer_observation', h.observation_capacitation,
                    'integrated_daily_salary', COALESCE(h.diary_salary, s.sdi),
                    'bank', h.bank,
                    'interbank_key', h.bank_account,
                    'blood_type', h.blood_type,
                    'dopping', h.dopping,
                    'card', h.cartilla,
                    'staff_in_charge', h.personal_in_charge,
                    'experience', h.experience,
                    'recruiter', h.recluter_id,
                    'service', h.service_id,
                    'turno', h.shift_id,
                    'is_active', u.is_active,
                    'lote_imss', u.lote_imss,
                    'entry_date', TO_CHAR(u.created_at, 'YYYY-MM-DD'),
                    'educationLevel', h.education_level,
                    'firstJob', h.first_job,
                    'actitudServicio', h.service_attitude,
                    'apegoNormas', h.adherence_to_rules,
                    'juicio', h.judgment,
                    'trabajoEquipo', h.teamwork,
                    'beneficiaries', COALESCE(beneficiaries_data.beneficiaries, '[]'),
                    'jobs', COALESCE(jobs_data.jobs, '[]'),
                    'documentos', COALESCE(docs_data.documentos, '[]')
                ) AS result
                FROM search_results h
                JOIN users u ON h.id_user = u.id
                LEFT JOIN salaries s ON u.salary_id = s.id
                LEFT JOIN LATERAL (
                    SELECT json_agg(json_build_object(
                        'id', b.id,
                        'beneficiary_name', b.full_name,
                        'relationship', b.relationship,
                        'percentage', b.percentage_benefit
                    )) AS beneficiaries
                    FROM beneficiaries b
                    WHERE b.id_hire = h.id
                ) beneficiaries_data ON true
                LEFT JOIN LATERAL (
                    SELECT json_agg(json_build_object(
                        'id', e.id,
                        'nameJob', e.company_name,
                        'period', e.company_period,
                        'lastSalary', e.last_salary,
                        'zoneJob', e.zone,
                        'schedule', e.schedule,
                        'observations', e.observation,
                        'reasonForResignation', e.motive_leave
                    )) AS jobs
                    FROM employement_history e
                    WHERE e.id_hire = h.id
                ) jobs_data ON true
                LEFT JOIN LATERAL (
                    SELECT json_agg(
                        json_build_object(
                            'id', d.id,
                            'nombre', d.document_name,
                            'completo', d.status
                        ) ORDER BY d.id ASC
                    ) AS documentos
                    FROM document_checklists d
                    WHERE d.id_hire = h.id
                ) docs_data ON true
            ) sub;
        """
        search_sql = search_sql.format(additional_filter=additional_filter)
        
        params = {"search_term": search_term}
        if filter_status == 'Ultimos Creados':
            params["filter_date"] = filter_value
        else:
            params["filter_status"] = filter_status
        
        res = db.session.execute(
            text(search_sql), 
            params
        ).fetchone()

        hires_data = res.hires if res.hires is not None else []
        
        return response(hires_data, 200)
        
    except Exception as e:
        return response_error(str(e), 500)


def get_all_job_positions():
    try:
        categories = db.session.query(CategoriesUser).all()
        json_categories = [categories.to_dict() for categories in categories]
        return response(json_categories)
    except Exception as e:
        return response_error(str(e), 500)


def update_observation(id, data):
    try:
        hire = Hires.query.get_or_404(id)
        hire.observation_capacitation = data.get('observation')
        db.session.commit()
        return response("Observation updated successfully", 200)
    except Exception as e:
        return response_error(str(e), 500)


def add_beneficiary(id, data):
    try:
        hire = Hires.query.get_or_404(id)
        percentage_value = float(data.get('percentage')) if data.get('percentage') is not None else None
        new_beneficiary = Beneficiaries(
            id_hire=hire.id,
            full_name=data.get('beneficiary_name'),
            relationship=data.get('relationship'),
            percentage_benefit=percentage_value
        )
        db.session.add(new_beneficiary)
        db.session.commit()
        return response({'message': 'Beneficiary added successfully', 'id': new_beneficiary.id}, 200)
    except Exception as e:
        return response_error(str(e), 500)


def update_beneficiaries(data):
    try:
        mappings = [{
            "id": ben["id"],
            "full_name": ben["beneficiary_name"],
            "relationship": ben["relationship"],
            "percentage_benefit": ben["percentage"]
        } for ben in data]

        db.session.bulk_update_mappings(Beneficiaries, mappings)
        db.session.commit()
        return response("Beneficiaries updated successfully", 200)
    except Exception as e:
        db.session.rollback()
        return response_error(str(e), 500)


def delete_beneficiary(id):
    try:
        beneficiary = Beneficiaries.query.get_or_404(id)
        db.session.delete(beneficiary)
        db.session.commit()
        return response("Beneficiary deleted successfully", 200)
    except Exception as e:
        db.session.rollback()
        return response_error(str(e), 500)


def add_job(id, data):
    try:
        hire = Hires.query.get_or_404(id)
        new_job = EmployementHistory(
            id_hire=hire.id,
            company_name=data.get('nameJob'),
            company_period=data.get('period'),
            zone=data.get('zoneJob'),
            schedule=data.get('schedule'),
            last_salary=data.get('lastSalary'),
            observation=data.get('observations'),
            motive_leave=data.get('reasonForResignation'),
        )
        db.session.add(new_job)
        db.session.commit()
        return response({'message': 'Add job successfully', 'id': new_job.id}, 200)
    except Exception as e:
        return response_error(str(e), 500)


def update_jobs(data):
    try:
        mappings = [{
            "id": job["id"],
            "company_name": job["nameJob"],
            "company_period": job["period"],
            "zone": job["zoneJob"],
            "schedule": job["schedule"],
            "last_salary": job["lastSalary"],
            "observation": job["observations"],
            "motive_leave": job["reasonForResignation"]
        } for job in data]

        db.session.bulk_update_mappings(EmployementHistory, mappings)
        db.session.commit()
        return response("Jobs updated successfully", 200)
    except Exception as e:
        db.session.rollback()
        return response_error(str(e), 500)


def update_documents(data):
    try:
        mappings = [{
            "id": doc["id"],
            "status": doc["completo"],
            "prorroga": doc.get("prorroga", False)
        } for doc in data]

        db.session.bulk_update_mappings(DocumentChecklists, mappings)
        db.session.commit()
        return response("Documents updated successfully", 200)
    except Exception as e:
        db.session.rollback()
        return response_error(str(e), 500)


def search_hiring_by_curp(curp):
    try:
        if not CURP_PATTERN.match(curp):
            return response_error("Invalid CURP structure", 400)

        hire = (
            db.session.query(Hires)
            .join(Users)
            .options(
                joinedload(Hires.user).load_only(
                    Users.id, Users.id_grip_external, Users.first_name, Users.second_name,
                    Users.last_name, Users.second_last_name, Users.email, Users.cellphone,
                    Users.birthday, Users.is_active, Users.lote_imss, Users.created_at,
                    Users.id_category
                ),
                joinedload(Hires.beneficiaries).load_only(
                    Beneficiaries.id, Beneficiaries.full_name, Beneficiaries.relationship, Beneficiaries.percentage_benefit
                ),
                joinedload(Hires.employement_history).load_only(
                    EmployementHistory.id, EmployementHistory.company_name, EmployementHistory.company_period,
                    EmployementHistory.last_salary, EmployementHistory.zone, EmployementHistory.schedule,
                    EmployementHistory.observation, EmployementHistory.motive_leave
                ),
                joinedload(Hires.document_checklists).load_only(
                    DocumentChecklists.id, DocumentChecklists.document_name, DocumentChecklists.status
                )
            )
            .filter(Hires.curp == curp)
            .first()
        )

        if not hire:
            return response_error("No hiring record found for the provided CURP", 404)

        hire_data = {
            "id": hire.id,
            "id_user": hire.id_user,
            "id_grip_external": hire.user.id_grip_external,
            "first_name": hire.user.first_name,
            "second_name": hire.user.second_name,
            "first_last_name": hire.user.last_name,
            "second_last_name": hire.user.second_last_name,
            "email": hire.user.email,
            "phone_number": hire.user.cellphone,
            "birth_date": hire.user.birthday,
            "position": hire.user.id_category,
            "status": hire.status_hire,
            "gender": hire.gender,
            "nationality": hire.nationality,
            "marital_status": hire.marital_status,
            "address": hire.address,
            "postal_code": hire.postal_code,
            "curp": hire.curp,
            "rfc": hire.rfc,
            "nss": hire.nss,
            "infonavit": hire.infonavit,
            "fonacot": hire.fonacot,
            "training_date": hire.capacitation_date,
            "trainer_observation": hire.observation_capacitation,
            "integrated_daily_salary": hire.diary_salary,
            "bank": hire.bank,
            "interbank_key": hire.bank_account,
            "blood_type": hire.blood_type,
            "dopping": hire.dopping,
            "card": hire.cartilla,
            "staff_in_charge": hire.personal_in_charge,
            "experience": hire.experience,
            "recruiter": hire.recluter_id,
            "service": hire.service_id,
            "turno": hire.shift_id,
            "is_active": hire.user.is_active,
            "lote_imss": hire.user.lote_imss,
            "entry_date": hire.user.created_at,
            "educationLevel": hire.education_level,
            "firstJob": hire.first_job,
            "actitudServicio": hire.service_attitude,
            "apegoNormas": hire.adherence_to_rules,
            "juicio": hire.judgment,
            "trabajoEquipo": hire.teamwork,
            "beneficiaries": [
                {
                    "id": b.id,
                    "beneficiary_name": b.full_name,
                    "relationship": b.relationship,
                    "percentage": b.percentage_benefit
                } for b in hire.beneficiaries
            ],
            "jobs": [
                {
                    "id": j.id,
                    "nameJob": j.company_name,
                    "period": j.company_period,
                    "lastSalary": j.last_salary,
                    "zoneJob": j.zone,
                    "schedule": j.schedule,
                    "observations": j.observation,
                    "reasonForResignation": j.motive_leave
                } for j in hire.employement_history
            ],
            "documentos": [
                {
                    "id": d.id,
                    "nombre": d.document_name,
                    "completo": d.status
                } for d in hire.document_checklists
            ]
        }

        return response(hire_data, 200)

    except Exception as e:

        return response_error(f"An unexpected error occurred: {str(e)}", 500)


def update_loans_to_incomplete_documents(id_quincena: int, status: int):
    """
    Actualiza el estado de las deudas de los usuarios que no tienen la documentación completa.
    Si los documentos ya no están pendientes, elimina las deudas correspondientes.
    """
    session = db.session
    try:
        recent_hires = fetch_recent_hires(session, id_quincena)
        if not recent_hires:
            return

        incomplete_users = validate_documents(recent_hires)

        loans_to_this_quincena = session.query(LoanManagement).filter_by(
            loan_type_id=5,
            date_end=recent_hires[0].cut_quincena,
            status=1
        ).all()

        if len(incomplete_users) > 0:
            list_id_user_incomplete = [i['id_user'] for i in incomplete_users]
            for loan in loans_to_this_quincena:
                if loan.user_id not in list_id_user_incomplete:
                    session.query(LoanHistory).filter_by(
                        loan_id=loan.id,
                        user_id=loan.user_id,
                        status=1
                    ).delete(synchronize_session=False)
                    session.query(LoanManagement).filter_by(
                        id=loan.id,
                        user_id=loan.user_id,
                        status=1
                    ).delete(synchronize_session=False)
                else:
                    session.query(LoanManagement).filter_by(id=loan.id).update({"status": 3}, synchronize_session=False)
                    session.query(LoanHistory).filter_by(loan_id=loan.id).update({"status": 3}, synchronize_session=False)
            session.commit()

        else:
            delete_loans(session, loans_to_this_quincena, recent_hires[0].cut_quincena)
            session.commit()

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def check_if_user_complete_documents(id_quincena: int, status: int):
    session = db.session
    try:
        recent_hires = fetch_recent_hires(session, id_quincena)
        if not recent_hires:
            return

        incomplete_users = validate_documents(recent_hires)

        loans_to_this_quincena = session.query(LoanManagement).filter_by(
            loan_type_id=5,
            date_end=recent_hires[0].cut_quincena,
            status=1
        ).all()

        if len(incomplete_users) > 0:
            loans = []
            loan_histories = []
            amount_to_pay_record = session.query(CostAbsence.cost).filter_by(type=5).first()
            if amount_to_pay_record is None:
                amount_to_pay = 250
            else:
                amount_to_pay = amount_to_pay_record.cost
            list_id_loans = [l.user_id for l in loans_to_this_quincena]

            for user in incomplete_users:
                if user['id_user'] not in list_id_loans:
                    loan = LoanManagement(
                        user_id=user['id_user'],
                        loan_type_id=5,
                        amount_total=amount_to_pay,
                        amount_pay=amount_to_pay,
                        number_of_payments=1,
                        date_init=user['date_pay'],
                        date_end=user['date_pay'],
                        status=1
                    )
                    loans.append(loan)

            if loans:
                session.add_all(loans)
                session.flush()

                for loan in loans:
                    loan_histories.append({
                        "loan_id": loan.id,
                        "user_id": loan.user_id,
                        "amount_pay": amount_to_pay,
                        "date_pay": loan.date_init,
                        "observations": "DOCUMENTACIÓN INCOMPLETA",
                        "status": 1
                    })

                session.bulk_insert_mappings(LoanHistory, loan_histories)
                session.commit()

            list_id_user_incomplete = [i['id_user'] for i in incomplete_users]
            for loan in loans_to_this_quincena:
                if loan.user_id not in list_id_user_incomplete:
                    session.query(LoanHistory).filter_by(
                        loan_id=loan.id,
                        user_id=loan.user_id,
                        status=1
                    ).delete(synchronize_session=False)
                    session.query(LoanManagement).filter_by(
                        id=loan.id,
                        user_id=loan.user_id,
                        status=1
                    ).delete(synchronize_session=False)

            session.commit()

        else:
            delete_loans(session, loans_to_this_quincena, recent_hires[0].cut_quincena)
            session.commit()

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()



def fetch_recent_hires(session, id_quincena):
    query = text("""
            WITH user_quincena_count AS (
            SELECT
                h.id_user,
                COUNT(*) AS quincena_count
            FROM hires h
            JOIN users u ON h.id_user = u.id
            JOIN calendar_nomina cn_all ON cn_all.cut_quincena >= u.created_at
            LEFT JOIN roles r ON u.role = r.id
            WHERE
                h.status_hire = 'Contratado'
                AND u.is_active = TRUE
                AND (r.is_administrative != true or r.is_administrative is null)
                -- Solo hasta la quincena objetivo
                AND cn_all.cut_quincena <= (
                SELECT cut_quincena
                FROM calendar_nomina
                WHERE id = :id_quincena
                )
            GROUP BY h.id_user
            )
            SELECT
            h.id_user,
            h.gender,
            u.created_at  AS hired_date,
            cn.cut_quincena,
            COALESCE(
                json_agg(
                json_build_object(
                    'id',     dc.id,
                    'name',   dc.document_name,
                    'status', dc.status
                )
                )
            , '[]') AS documents
            FROM hires h
            JOIN users u ON h.id_user = u.id
            JOIN document_checklists dc ON h.id = dc.id_hire
            JOIN calendar_nomina cn ON cn.id = :id_quincena
            -- Nos quedamos solo con usuarios con ≤ 4 quincenas
            JOIN user_quincena_count uq ON uq.id_user = h.id_user
            AND uq.quincena_count <= 4
            GROUP BY h.id_user, h.gender, u.created_at, cn.cut_quincena;
        """)

    return session.execute(query, {"id_quincena": id_quincena}).fetchall()


def validate_documents(recent_hires):
    base_mandatory_docs = [
        'Acta de nacimiento', 'CURP', 'RFC', 'NSS', 'INE',
        'Comprobante de domicilio', 'Número de cuenta CLABE',
        'Comprobante de estudios', 'Certificado medico',
        'Antecedentes no penales federales'
    ]

    incomplete_users = []
    for hire in recent_hires:
        required = base_mandatory_docs.copy()
        if hire.gender and hire.gender.lower() != 'femenino':
            required.append('Cartilla')

        done = [d['name'] for d in hire.documents if d['status'] and d['name'] in required]
        missing = [d for d in required if d not in done]

        if missing:
            incomplete_users.append({
                'id_user': hire.id_user,
                'date_pay': hire.cut_quincena
            })
    return incomplete_users


def delete_loans(session, loans_to_this_quincena, cut_quincena):
    if loans_to_this_quincena:
        session.query(LoanHistory).filter(
            LoanHistory.loan_id.in_(
                session.query(LoanManagement.id).filter_by(
                    loan_type_id=5,
                    date_end=cut_quincena,
                    status=1
                )
            )
        ).delete(synchronize_session=False)

        session.query(LoanManagement).filter_by(
            loan_type_id=5,
            date_end=cut_quincena,
            status=1
        ).delete(synchronize_session=False)


# utils methods
def generate_id_external():
    session = db.session()
    try:
        query = text("""
            SELECT MAX(
            CASE 
                WHEN id_grip_external ~ '^[0-9]+$' THEN id_grip_external::numeric 
                ELSE 0 
            END
            ) AS max_numeric_id
            FROM users;        
        """)
        result = session.execute(query).fetchone()
        max_id = result[0]
        return str(max_id + 1)
    except Exception as e:
        return response_error(str(e), 500)
    finally:
        session.close()


def update_list_notification(data):
    try:
        EmailNotificationsNewContracts.query.delete()
        emails = data['emails'].replace(' ', '').split(',')
        for email in emails:
            value = EmailNotificationsNewContracts.query.filter_by(email=email).first()
            if value is None:
                db.session.add(
                    EmailNotificationsNewContracts(
                        email=email
                    )
                )
        db.session.commit()
        return response("Email notification updated successfully", 200)
    except Exception as e:
        return response_error(str(e), 500)
    finally:
        db.session.close()


def get_list_notifications():
    emails = ",".join([email.email for email in EmailNotificationsNewContracts.query.all()])
    return {
        "emails": emails
    }, 200
