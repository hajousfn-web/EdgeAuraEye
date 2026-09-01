import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer, TfidfTransformer
from sklearn.linear_model import RidgeClassifier
from sklearn.model_selection import train_test_split


class LanguageDetectorEngine:
    """Lightweight multi-language text detector for Ego dashboard."""

    DEFAULT_LANGUAGE_DATA = {
        'en': [
            'hello world',
            'welcome to the system',
            'live monitoring is active',
            'this is an english message',
            'status okay and ready',
            'hello my friend',
            'system is running normally',
            'edge ai is online',
            'human guard monitoring is active',
        ],
        'ar': [
            'مرحبا بالعالم',
            'النظام يعمل بشكل صحيح',
            'هذا نص عربي بسيط',
            'الإنذار نشط الآن',
            'أهلا بكم في المشروع',
            'المراقبة المحلية جاهزة',
            'اللغة العربية معروفة',
            'الرصد الحي يعمل بشكل مستقر',
            'تم اكتشاف حركة غير طبيعية',
        ],
        'it': [
            'ciao mondo',
            'il sistema è attivo',
            'questo testo è in italiano',
            'il monitoraggio locale è in corso',
            'benvenuto nel sistema',
            'è stata rilevata un\'allerta nella zona',
            'il sistema funziona correttamente',
            'la cattura del rischio è attiva',
            'la sicurezza locale è pronta',
        ],
        'es': [
            'hola mundo',
            'el sistema está activo',
            'este texto está en español',
            'la vigilancia local está en curso',
            'bienvenido al sistema',
            'se detectó una alerta en la zona',
            'el sistema funciona correctamente',
            'la captura del riesgo está activa',
            'la seguridad local está lista',
        ],
        'fr': [
            'bonjour le monde',
            'le système est actif',
            'ce texte est en français',
            'la surveillance locale est en cours',
            'bienvenue dans le système',
            'une alerte a été détectée dans la zone',
            'le système fonctionne correctement',
            'la capture du risque est active',
            'la sécurité locale est prête',
        ],
        'zh': [
            '你好世界',
            '系统已启动',
            '这是中文文本',
            '本地监控正在运行',
            '检测到区域警报',
            '系统运行正常',
            '风险捕获已开启',
            '视觉处理模块在线',
            '环境安全监测正常',
        ],
        'ko': [
            '안녕하세요 세계',
            '시스템이 정상 작동 중입니다',
            '이 문구는 한국어입니다',
            '로컬 모니터링이 진행 중입니다',
            '구역에서 경고가 감지되었습니다',
            '시스템이 안정적으로 작동하고 있습니다',
            '위험 캡처가 활성화되었습니다',
            '비전 처리 모듈이 온라인 상태입니다',
            '현장 보안 통제가 준비되었습니다',
        ],
        'zgh': [
            'ⴰⵣⵓⵍⵉ ⵏ ⵡⴰⵏⵙ',
            'ⴰⵙⵉⵙⵜⴰⵎ ⵢⴰⵡⵉⵏ ⵏ ⵍⵎⴰⵍ ⵉⵣⵣⴰⵍ',
            'ⵏⵏⴰⵙⵉ ⵜⵉⵎⵣⵉⵖⵜ ⵏ ⵍⵙⵎⴰⵍ',
            'ⴰⵡⵍⴰⵢ ⵏ ⵍⵎⵓⵏⵉⵟⵓⵔⵉⵏⵍ ⴰⵙⵉⵏ ⵉⵣⵔⴰⵏ',
            'ⵜⵓⵎⵉⵍⵉⴽⵜ ⵏ ⵍⵎⴰⵡⵔⵉ ⵉⵙⵉⵎ ⵉⵣⵔⴰⵏ',
            'ⵡⴰⵔ ⴰⵙⵉⵍⵉ ⵏ ⵍⵙⵡⵉⵏ ⵉⵏⵙⴰⵍ',
            'ⵍⵖⵔⵉⵣ ⵏ ⵍⵎⵓⵏⵉⵟⵓⵔⵉⵏⵍ ⵢⴰⴹⵔⴰⵏ',
            'ⵉⵎⵥⵍⵉ ⴰⵢⵏⵉⵍ ⵏ ⵍⴰⵣⵓⵍ',
            'ⴰⵙⵎⴰⵍ ⵏ ⵍⵏⵉⵡⵔⵉ ⵉⵍⵉ ⵡⴰⵔⵉⵣ',
        ],
    }

    def __init__(self, dataset_path: str | None = None):
        if dataset_path:
            self.df = self._load_dataset(dataset_path)
        else:
            self.df = self._build_default_dataset()

        self.vectorizer = CountVectorizer(lowercase=True)
        self.transformer = TfidfTransformer()
        self.model = RidgeClassifier()
        self._train_model()

    def _load_dataset(self, dataset_path: str) -> pd.DataFrame:
        df = pd.read_csv(dataset_path)
        required_columns = {'Text', 'language'}
        missing_columns = required_columns - set(df.columns)
        if missing_columns:
            raise ValueError(f"Dataset is missing required columns: {sorted(missing_columns)}")

        df = df[['Text', 'language']].dropna().copy()
        df['Text'] = df['Text'].astype(str)
        df['language'] = df['language'].astype(str)

        if df.empty:
            raise ValueError('Dataset is empty. Please provide a valid language dataset.')

        return df

    def _build_default_dataset(self) -> pd.DataFrame:
        rows = []
        for language, samples in self.DEFAULT_LANGUAGE_DATA.items():
            for sample in samples:
                rows.append({'Text': sample, 'language': language})
        return pd.DataFrame(rows)

    def _train_model(self):
        X_train, _, y_train, _ = train_test_split(
            self.df['Text'],
            self.df['language'],
            test_size=0.25,
            random_state=2551,
            shuffle=True,
        )

        X_train_counts = self.vectorizer.fit_transform(X_train)
        X_train_tfidf = self.transformer.fit_transform(X_train_counts)
        self.model.fit(X_train_tfidf, y_train)

    def predict_language(self, text: str) -> str:
        if text is None or not str(text).strip():
            return 'unknown'

        prepared = str(text).strip()
        if len(prepared) < 1:
            return 'unknown'

        transformed = self.transformer.transform(self.vectorizer.transform([prepared]))
        predicted = self.model.predict(transformed)
        return str(predicted[0])

    def detect(self, text: str) -> dict:
        language = self.predict_language(text)
        return {
            'language': language,
            'language_name': {
                'en': 'English',
                'ar': 'Arabic',
                'es': 'Spanish',
                'fr': 'French',
                'zh': 'Chinese',
                'ko': 'Korean',
                'it': 'Italian',
                'zgh': 'Amazigh',
                'unknown': 'Unknown',
            }.get(language, language),
            'text': text,
        }


def detect_language_text(text: str, dataset_path: str | None = None) -> dict:
    detector = LanguageDetectorEngine(dataset_path)
    return detector.detect(text)
