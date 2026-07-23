LOGIN_URL = "https://clinico.rayenaps.cl/"
API_BASE_URL = "https://clinico.rayenaps.cl"
LOG_FILE = "login_automation.log"

EXIT_OK = 0
EXIT_ERROR = 1

USER_ID_PROMPT = "Ingrese identificador de usuario: "
DATE_PROMPT = "Ingrese fecha (dd-mm-yyyy): "
DATE_FORMAT = "%d-%m-%Y"
DATE_FORMAT_LOG = "%Y-%m-%d"

PLACEHOLDERS = [
    "{PACIENTE}",
    "{RUT}",
    "{FECHA}",
    "{RAZON}",
    "{TIPO_ATENCION}",
    "{OBSERVACION}",
    "{HORA}",
]

INSTRUMENTO_PREFIXES = ["ME,", "EN,", "PS,", "TO,", "NU,", "KT,"]

SEPARADOR_ANCHO = 70
ESTADO_INICIADO = "Iniciado"
CAMPOS_POR_FILA = 9

ENV_USER_PREFIX = "USERS_"
ENV_LOCATION_SUFFIX = "_LOCATION"
ENV_USERNAME_SUFFIX = "_USERNAME"
ENV_PASSWORD_SUFFIX = "_PASSWORD"
