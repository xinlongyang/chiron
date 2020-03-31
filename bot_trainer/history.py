from rasa.core.tracker_store import MongoTrackerStore, DialogueStateTracker
from rasa.core.domain import Domain
import pandas as pd
from datetime import datetime

class ChatHistory:
    def __init__(self, domainFile: str, mongo_url :str, mongo_db = 'conversation'):
        self.domain = Domain.load(domainFile)
        self.tracker = MongoTrackerStore(domain=self.domain, host=mongo_url, db=mongo_db)

    def fetch_chat_history(self, sender, latest_history = False):
        events = self.__fetch_user_history(sender, latest_history=latest_history)
        return list(self.__prepare_data(events))

    def fetch_chat_users(self):
        return self.tracker.keys()

    def __prepare_data(self, events, show_session = False):
        bot_action = None
        for i in range(events.__len__()):
            event = events[i]
            event_data = event.as_dict()
            if event_data['event'] not in ['action', 'rewind']:
                result = {'event': event_data['event'], 'time': datetime.fromtimestamp(event_data['timestamp']).time(), 'date': datetime.fromtimestamp(event_data['timestamp']).date()}

                if event_data['event'] not in ['session_started', 'rewind']:
                    result['text'] = event_data['text']

                if event_data['event'] == 'user':
                    parse_data = event_data['parse_data']
                    result['intent'] = parse_data['intent']['name']
                    result['confidence'] = parse_data['intent']['confidence']
                elif event_data['event'] == 'bot':
                    if bot_action:
                        result['action'] = bot_action

                if event_data['event'] == 'session_started' and not show_session:
                    continue
                yield result
            else:
                bot_action = event_data['name'] if event_data['event'] == 'action' else None

    def __fetch_user_history(self, sender_id, latest_history = True):
        if latest_history:
            return self.tracker.retrieve(sender_id).as_dialogue().events
        else:
            user_conversation = self.tracker.conversations.find_one({"sender_id": sender_id})
            return DialogueStateTracker.from_dict(sender_id, list(user_conversation['events']), self.domain.slots).as_dialogue().events

    def visitor_hit_fallback(self):
        data_frame = self.__fetch_history_metrics()
        fallback_count = data_frame[data_frame['name'] == 'action_default_fallback'].count()['name']
        total_count = data_frame.count()['name']
        return { 'fallback_count': fallback_count, 'total_count' : total_count  }

    def conversation_steps(self):
        '''
        data_frame = data_frame.groupby(['sender_id', data_frame.event.ne('session_started')])
        data_frame = data_frame.size().reset_index()
        data_frame.rename(columns={0: 'count'}, inplace=True)
        data_frame = data_frame[data_frame['event'] != 0]
        return data_frame.to_json(orient='records')
        '''
        data_frame = self.__fetch_history_metrics()
        data_frame['prev_event'] = data_frame['event'].shift()
        data_frame['prev_timestamp'] = data_frame['timestamp'].shift()
        data_frame.fillna('', inplace=True)
        data_frame = data_frame[((data_frame['event'] == "bot") & (data_frame['prev_event'] == 'user'))]
        return data_frame.groupby(['sender_id']).count().reset_index()[['sender_id', 'event']].to_json(orient='records')

    def conversation_steps(self):
        '''
        data_frame = data_frame.groupby(['sender_id', data_frame.event.ne('session_started')])
        data_frame = data_frame.size().reset_index()
        data_frame.rename(columns={0: 'count'}, inplace=True)
        data_frame = data_frame[data_frame['event'] != 0]
        return data_frame.to_json(orient='records')
        '''
        data_frame = self.__fetch_history_metrics()
        data_frame['prev_event'] = data_frame['event'].shift()
        data_frame['prev_timestamp'] = data_frame['timestamp'].shift()
        data_frame.fillna('', inplace=True)
        data_frame = data_frame[((data_frame['event'] == "bot") & (data_frame['prev_event'] == 'user'))]
        return data_frame.groupby(['sender_id']).count().reset_index()[['sender_id', 'event']].to_json(orient='records')

    def conversation_time(self):
        data_frame = self.__fetch_history_metrics()
        data_frame['prev_event'] = data_frame['event'].shift()
        data_frame['prev_timestamp'] = data_frame['timestamp'].shift()
        data_frame.fillna('', inplace=True)
        data_frame = data_frame[((data_frame['event'] == "bot") & (data_frame['prev_event'] == 'user'))]
        data_frame['time'] = pd.to_datetime(data_frame['timestamp'], unit='s') - pd.to_datetime(data_frame['prev_timestamp'], unit='s')
        return data_frame[['sender_id', 'time']].groupby('sender_id').sum().reset_index().to_json(orient='records')

    def __fetch_history_metrics(self, show_session=False, filter_columns=None):
        filter_events = ['user', 'bot']
        if show_session:
            filter_events.append('session_started')

        if not filter_columns:
            filter_columns = ['sender_id', 'event', 'name', 'text', 'timestamp', 'input_channel', 'message_id']
        records = self.tracker.conversations.find()
        data_frame = pd.DataFrame(list(records))
        data_frame = data_frame.explode(column='events')
        data_frame = pd.concat([data_frame.drop(['events'], axis=1), data_frame['events'].apply(pd.Series)], axis=1)
        data_frame.fillna('', inplace=True)
        data_frame['name'] = data_frame['name'].shift()
        data_frame = data_frame[data_frame['event'].isin(filter_events)]
        data_frame = data_frame[filter_columns]
        return data_frame