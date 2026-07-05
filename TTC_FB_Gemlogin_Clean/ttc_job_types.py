# -*- coding: utf-8 -*-
"""
ttc_job_types.py — Định nghĩa job TTC, bảng endpoint, helpers chuẩn hóa.

Không phụ thuộc vào bất kỳ module GUI hay runtime nào.
"""

import re
import html
from enum import Enum


# =====================================================================
# Bảng endpoint TTC tập trung — không rải URL khắp mã nguồn
# =====================================================================

TTC_BASE_URL = "https://tuongtaccheo.com"

TTC_ENDPOINTS = {
    # job_type_key -> (get_url, claim_url)
    "ttc_like_post_vip_cheo": (
        f"{TTC_BASE_URL}/kiemtien/likepostvipcheo/getpost.php",
        f"{TTC_BASE_URL}/kiemtien/likepostvipcheo/nhantien.php",
    ),
    "ttc_like_post_vip_re": (
        f"{TTC_BASE_URL}/kiemtien/likepostvipre/getpost.php",
        f"{TTC_BASE_URL}/kiemtien/likepostvipre/nhantien.php",
    ),
    "ttc_reaction_vip_cheo": (
        f"{TTC_BASE_URL}/kiemtien/camxucvipcheo/getpost.php",
        f"{TTC_BASE_URL}/kiemtien/camxucvipcheo/nhantien.php",
    ),
    "ttc_reaction_vip_re": (
        f"{TTC_BASE_URL}/kiemtien/camxucvipre/getpost.php",
        f"{TTC_BASE_URL}/kiemtien/camxucvipre/nhantien.php",
    ),
    "ttc_comment": (
        f"{TTC_BASE_URL}/kiemtien/cmtcheo/getpost.php",
        f"{TTC_BASE_URL}/kiemtien/cmtcheo/nhantien.php",
    ),
    "ttc_follow": (
        f"{TTC_BASE_URL}/kiemtien/subcheo/getpost.php",
        f"{TTC_BASE_URL}/kiemtien/subcheo/nhantien.php",
    ),
    "ttc_like_page": (
        f"{TTC_BASE_URL}/kiemtien/likepagecheo/getpost.php",
        f"{TTC_BASE_URL}/kiemtien/likepagecheo/nhantien.php",
    ),
}

TTC_AUTH_URL = f"{TTC_BASE_URL}/logintoken.php"
TTC_SET_UID_URL = f"{TTC_BASE_URL}/cauhinh/datnick.php"

# =====================================================================
# Tất cả 7 loại job được hỗ trợ
# =====================================================================

ALL_JOB_TYPES = list(TTC_ENDPOINTS.keys())

# =====================================================================
# Nhóm action_group
# =====================================================================

ACTION_GROUP_MAP = {
    "ttc_like_post_vip_cheo": "reaction",
    "ttc_like_post_vip_re": "reaction",
    "ttc_reaction_vip_cheo": "reaction",
    "ttc_reaction_vip_re": "reaction",
    "ttc_comment": "comment",
    "ttc_follow": "follow",
    "ttc_like_page": "page_like",
}

# Nhóm loại job theo action_group
ACTION_GROUPS_BLOCKED_BY = {
    # action_group -> list[job_type] bị ảnh hưởng khi group bị block
    "reaction": [
        "ttc_like_post_vip_cheo",
        "ttc_like_post_vip_re",
        "ttc_reaction_vip_cheo",
        "ttc_reaction_vip_re",
    ],
    "comment": ["ttc_comment"],
    "follow": ["ttc_follow"],
    "page_like": ["ttc_like_page"],
}

# =====================================================================
# Reaction type mapping TTC -> nội bộ
# =====================================================================

VALID_REACTIONS = {"LIKE", "LOVE", "CARE", "HAHA", "WOW", "SAD", "ANGRY"}

REACTION_NORMALIZE_MAP = {
    "like": "LIKE",
    "thich": "LIKE",
    "love": "LOVE",
    "yeu thich": "LOVE",
    "care": "CARE",
    "thuong thuong": "CARE",
    "haha": "HAHA",
    "wow": "WOW",
    "sad": "SAD",
    "buon": "SAD",
    "angry": "ANGRY",
    "phan no": "ANGRY",
}


def normalize_reaction_type(raw: str) -> str:
    """Chuẩn hóa reaction type từ dữ liệu TTC về dạng nội bộ.

    TTC trả về loaicx như: LOVE, HAHA, WOW, SAD, ANGRY, CARE.
    Mặc định LIKE nếu không xác định được.
    """
    if not raw:
        return "LIKE"
    upper = str(raw).upper().strip()
    if upper in VALID_REACTIONS:
        return upper
    lower = str(raw).lower().strip()
    return REACTION_NORMALIZE_MAP.get(lower, "LIKE")


# =====================================================================
# Normalize job type
# =====================================================================

def normalize_job_type(job_type: str) -> str:
    """Xác minh job_type hợp lệ, trả về chuỗi gốc nếu OK."""
    if job_type in ALL_JOB_TYPES:
        return job_type
    return ""


def get_action_group(job_type: str) -> str:
    """Lấy action_group từ job_type nội bộ."""
    return ACTION_GROUP_MAP.get(job_type, "unknown")


def get_endpoint_urls(job_type: str):
    """Lấy (get_url, claim_url) theo job_type.

    Raises KeyError nếu job_type không hợp lệ.
    """
    return TTC_ENDPOINTS[job_type]


# =====================================================================
# Tạo job_key xác định, ổn định, không trùng giữa endpoint
# =====================================================================

def make_job_key(job_type: str, idpost: str, reaction_type: str = "") -> str:
    """Tạo job key duy nhất.

    Format: <job_type>:<idpost>[:<reaction_type>]
    Không dùng riêng idpost vì hai endpoint có thể trả cùng id.
    """
    parts = [str(job_type), str(idpost or "")]
    if reaction_type:
        parts.append(str(reaction_type).upper())
    return ":".join(parts)


# =====================================================================
# Parse comment text từ trường nd của TTC
# =====================================================================

def parse_ttc_comment_text(nd: str) -> str:
    """Parser comment text an toàn từ trường nd của TTC.

    Quy tắc:
    1. Nếu nd có nội dung trong dấu nháy kép thì lấy nội dung đó.
    2. Nếu không có dấu nháy nhưng có nội dung hợp lệ thì dùng text đã strip.
    3. Decode HTML entity nếu có.
    4. Không cho comment rỗng.
    5. Giới hạn 500 ký tự.
    6. Không thay đổi nội dung ngoài làm sạch định dạng bao ngoài.
    """
    if not nd:
        return ""
    # Decode HTML entities nếu có
    text = html.unescape(str(nd))

    # Trích nội dung trong dấu nháy kép ngoài cùng
    match = re.search(r'"([^"]+)"', text)
    if match:
        result = match.group(1).strip()
    else:
        result = text.strip()

    # Giới hạn độ dài
    if len(result) > 500:
        result = result[:500]

    return result


# =====================================================================
# Normalize raw TTC job -> schema nội bộ
# =====================================================================

from interaction_history import normalize_object_id as _normalize_object_id_impl


def normalize_job(job_type: str, raw_data: dict) -> dict:
    """Chuyển raw job TTC về schema nội bộ duy nhất.

    Args:
        job_type: Một trong ALL_JOB_TYPES.
        raw_data: Dict thô từ API TTC.

    Returns:
        Dict schema nội bộ, luôn có đủ các key quan trọng.
        Trả về empty dict nếu thiếu dữ liệu bắt buộc.
    """
    if not isinstance(raw_data, dict):
        return {}

    idpost = str(raw_data.get("idpost") or "").strip()
    link = str(raw_data.get("link") or "").strip()
    action_group = get_action_group(job_type)

    # object_id: ưu tiên normalize từ link, fallback idpost
    object_id = _normalize_object_id_impl(link) if link else ""
    if not object_id:
        object_id = idpost
    if not object_id:
        return {}  # Thiếu dữ liệu bắt buộc

    # Reaction type (chỉ dùng cho reaction group)
    reaction_type = ""
    if action_group == "reaction":
        raw_loai = raw_data.get("loaicx") or ""
        # like_post type không có loaicx → mặc định LIKE
        if job_type in ("ttc_like_post_vip_cheo", "ttc_like_post_vip_re"):
            reaction_type = "LIKE"
        else:
            reaction_type = normalize_reaction_type(raw_loai) if raw_loai else "LIKE"

    # Comment text
    comment_text = ""
    if action_group == "comment":
        comment_text = parse_ttc_comment_text(raw_data.get("nd") or "")

    # job_key
    job_key = make_job_key(job_type, idpost, reaction_type)

    # buff_id dùng làm alias tương thích với JobQueue hiện có
    buff_id = job_key

    return {
        "job_id": job_key,
        "buff_id": buff_id,          # alias tương thích JobQueue
        "type": job_type,
        "action_group": action_group,
        "object_id": object_id,
        "link": link,
        "reaction_type": reaction_type,
        "comment_text": comment_text,
        "ttc_source": job_type,
        "idpost": idpost,            # giữ để gọi nhantien.php
        "raw_data": dict(raw_data),  # debug only, không để GUI phụ thuộc
    }


def normalize_jobs_list(job_type: str, raw_list: list) -> list:
    """Normalize danh sách raw jobs, lọc bỏ job không hợp lệ."""
    result = []
    for raw in raw_list or []:
        job = normalize_job(job_type, raw)
        if job:
            result.append(job)
    return result


def normalize_delay_range(min_delay, max_delay):
    """Chuẩn hóa cặp delay (min, max) về giá trị hợp lệ."""
    try:
        min_delay = int(min_delay)
        max_delay = int(max_delay)
    except (TypeError, ValueError):
        return 5, 15
    if min_delay < 0 or max_delay < 0:
        return 5, 15
    if min_delay > max_delay:
        min_delay, max_delay = max_delay, min_delay
    min_delay = min(min_delay, 3600)
    max_delay = min(max_delay, 3600)
    return min_delay, max_delay
