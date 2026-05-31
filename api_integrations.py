"""
Модуль для интеграции с различными API поиска мест
"""
import requests
from math import radians, sin, cos, sqrt, atan2
import os

class PlaceSearchAPI:
    """Базовый класс для API поиска мест"""
    
    @staticmethod
    def calculate_distance(lat1, lon1, lat2, lon2):
        """Вычисляет расстояние между двумя точками в метрах (формула Haversine)"""
        R = 6371000  # Радиус Земли в метрах
        
        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lat = radians(lat2 - lat1)
        delta_lon = radians(lon2 - lon1)
        
        a = sin(delta_lat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        distance = R * c
        return distance


class TwoGISAPI(PlaceSearchAPI):
    """API 2GIS для поиска мест"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv('TWOGIS_API_KEY')
        self.base_url = 'https://catalog.api.2gis.com/3.0'
    
    def search_places(self, latitude, longitude, query, radius=2000, limit=10):
        """
        Поиск мест через 2GIS API
        
        Документация: https://docs.2gis.com/ru/api/search/places/overview
        """
        if not self.api_key:
            raise ValueError("2GIS API key not provided")
        
        url = f"{self.base_url}/items"
        params = {
            'q': query,
            'point': f"{longitude},{latitude}",
            'radius': radius,
            'limit': limit,
            'key': self.api_key,
            'locale': 'ru_RU'
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            places = []
            
            for item in data.get('result', {}).get('items', []):
                place = self._parse_2gis_place(item, latitude, longitude)
                places.append(place)
            
            return places
        
        except Exception as e:
            print(f"Ошибка 2GIS API: {e}")
            return []
    
    def _parse_2gis_place(self, item, user_lat, user_lon):
        """Парсит данные места из ответа 2GIS"""
        point = item.get('point', {})
        place_lat = point.get('lat', 0)
        place_lon = point.get('lon', 0)
        
        distance = self.calculate_distance(user_lat, user_lon, place_lat, place_lon)
        
        # Извлекаем атрибуты
        rubrics = item.get('rubrics', [])
        place_type = rubrics[0].get('name', 'unknown') if rubrics else 'unknown'
        
        # Определяем атрибуты для психологического ранжирования
        attributes = self._infer_attributes_from_rubrics(rubrics)
        
        return {
            'name': item.get('name', 'Неизвестное место'),
            'place_type': place_type,
            'address': item.get('address_name', ''),
            'latitude': place_lat,
            'longitude': place_lon,
            'distance': distance,
            'rating': item.get('reviews', {}).get('rating', None),
            'reviews_count': item.get('reviews', {}).get('count', 0),
            'api_source': '2gis',
            'api_id': item.get('id', ''),
            'api_data': item,
            **attributes
        }
    
    def _infer_attributes_from_rubrics(self, rubrics):
        """Определяет психологические атрибуты на основе рубрик 2GIS"""
        attributes = {
            'avg_price': 'medium',
            'atmosphere': 'neutral',
            'capacity': 'medium',
            'activity_level': 'moderate'
        }
        
        rubric_names = [r.get('name', '').lower() for r in rubrics]
        
        # Эвристики на основе рубрик
        if any('кафе' in r or 'кофейня' in r for r in rubric_names):
            attributes['atmosphere'] = 'relaxing'
            attributes['activity_level'] = 'passive'
        
        elif any('бар' in r or 'паб' in r for r in rubric_names):
            attributes['atmosphere'] = 'noisy'
            attributes['activity_level'] = 'moderate'
        
        elif any('парк' in r or 'сквер' in r for r in rubric_names):
            attributes['atmosphere'] = 'quiet'
            attributes['capacity'] = 'large'
            attributes['avg_price'] = 'low'
        
        elif any('спорт' in r or 'фитнес' in r for r in rubric_names):
            attributes['atmosphere'] = 'energetic'
            attributes['activity_level'] = 'active'
            attributes['avg_price'] = 'high'
        
        return attributes


class YandexMapsAPI(PlaceSearchAPI):
    """API Yandex Maps для поиска мест"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv('YANDEX_API_KEY')
        self.base_url = 'https://search-maps.yandex.ru/v1/'
    
    def search_places(self, latitude, longitude, query, radius=2000, limit=10):
        """
        Поиск мест через Yandex Maps API
        
        Документация: https://yandex.ru/dev/maps/geosearch/
        """
        if not self.api_key:
            raise ValueError("Yandex API key not provided")
        
        url = f"{self.base_url}"
        params = {
            'apikey': self.api_key,
            'text': query,
            'll': f"{longitude},{latitude}",
            'spn': '0.02,0.02',  # Область поиска
            'lang': 'ru_RU',
            'results': limit,
            'type': 'biz'
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            places = []
            
            for feature in data.get('features', []):
                place = self._parse_yandex_place(feature, latitude, longitude)
                places.append(place)
            
            return places
        
        except Exception as e:
            print(f"Ошибка Yandex API: {e}")
            return []
    
    def _parse_yandex_place(self, feature, user_lat, user_lon):
        """Парсит данные места из ответа Yandex"""
        properties = feature.get('properties', {})
        geometry = feature.get('geometry', {})
        coordinates = geometry.get('coordinates', [0, 0])
        
        place_lon, place_lat = coordinates
        distance = self.calculate_distance(user_lat, user_lon, place_lat, place_lon)
        
        company_meta = properties.get('CompanyMetaData', {})
        
        return {
            'name': properties.get('name', 'Неизвестное место'),
            'place_type': company_meta.get('Categories', [{}])[0].get('name', 'unknown'),
            'address': company_meta.get('address', ''),
            'latitude': place_lat,
            'longitude': place_lon,
            'distance': distance,
            'api_source': 'yandex',
            'api_id': company_meta.get('id', ''),
            'api_data': feature
        }


class NominatimAPI(PlaceSearchAPI):
    """API Nominatim (OpenStreetMap) для поиска мест - бесплатный"""
    
    def __init__(self):
        self.base_url = 'https://nominatim.openstreetmap.org'
        self.headers = {
            'User-Agent': 'RoutsolWeb/1.0'
        }
    
    def search_places(self, latitude, longitude, query, radius=2000, limit=10):
        """Поиск мест через Nominatim API"""
        url = f"{self.base_url}/search"
        
        # Вычисляем bbox на основе радиуса
        # Примерно 0.01 градуса = ~1км
        delta = radius / 100000
        
        params = {
            'q': query,
            'format': 'json',
            'limit': limit,
            'viewbox': f"{longitude-delta},{latitude-delta},{longitude+delta},{latitude+delta}",
            'bounded': 1,
            'accept-language': 'ru'
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            results = response.json()
            places = []
            
            for result in results:
                place = self._parse_nominatim_place(result, latitude, longitude)
                if place['distance'] <= radius:
                    places.append(place)
            
            return places
        
        except Exception as e:
            print(f"Ошибка Nominatim API: {e}")
            return []
    
    def _parse_nominatim_place(self, result, user_lat, user_lon):
        """Парсит данные места из ответа Nominatim"""
        place_lat = float(result.get('lat', 0))
        place_lon = float(result.get('lon', 0))
        
        distance = self.calculate_distance(user_lat, user_lon, place_lat, place_lon)
        
        return {
            'name': result.get('display_name', 'Неизвестное место').split(',')[0],
            'place_type': result.get('type', 'unknown'),
            'address': result.get('display_name', ''),
            'latitude': place_lat,
            'longitude': place_lon,
            'distance': distance,
            'api_source': 'nominatim',
            'api_id': result.get('place_id', ''),
            'api_data': result
        }
    
    def reverse_geocode(self, latitude, longitude):
        """Получает адрес по координатам"""
        url = f"{self.base_url}/reverse"
        params = {
            'format': 'json',
            'lat': latitude,
            'lon': longitude,
            'accept-language': 'ru'
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            return result.get('display_name', f"{latitude}, {longitude}")
        
        except Exception as e:
            print(f"Ошибка reverse geocoding: {e}")
            return f"{latitude}, {longitude}"


# Фабрика для выбора API
def get_place_search_api(api_type='nominatim'):
    """
    Возвращает экземпляр API для поиска мест
    
    api_type: 'nominatim', '2gis', 'yandex'
    """
    if api_type == '2gis':
        return TwoGISAPI()
    elif api_type == 'yandex':
        return YandexMapsAPI()
    else:
        return NominatimAPI()
