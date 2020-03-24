import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from collections import deque
import datetime
import time
from iq import get_profit,fast_data,higher,lower,login,get_balance
from training import train_data
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout, LSTM, BatchNormalization
from tensorflow.keras.callbacks import TensorBoard, ModelCheckpoint
from tensorflow.compat.v1.keras.layers import CuDNNLSTM

gpus = tf.config.experimental.list_physical_devices('GPU')
if gpus:
  try:
    # Currently, memory growth needs to be the same across GPUs
    for gpu in gpus:
      tf.config.experimental.set_memory_growth(gpu, True)
    logical_gpus = tf.config.experimental.list_logical_devices('GPU')
    print(len(gpus), "Physical GPUs,", len(logical_gpus), "Logical GPUs")
  except RuntimeError as e:
    # Memory growth must be set before GPUs have been initialized
    print(e)

def preprocess_prediciton(iq):
    Actives = ['EURUSD','GBPUSD','EURJPY','AUDUSD']
    active = 'EURUSD'
    main = pd.DataFrame()
    current = pd.DataFrame()
    for active in Actives:
        if active == 'EURUSD':
            main = fast_data(iq,active).drop(columns = {'from','to'})
        else:
            current = fast_data(iq,active)
            current = current.drop(columns = {'from','to','open','min','max'})
            current.columns = [f'close_{active}',f'volume_{active}']
            main = main.join(current)
    
    df = main
    #duplis = df.loc[df.duplicated() == True] # the duplicates are explained by the volume 0 
    df.isnull().sum().sum() # there are no nans
    df.fillna(method="ffill", inplace=True)
    df = df.loc[~df.index.duplicated(keep = 'first')]
    
    df['MA_20'] = df['close'].rolling(window = 20).mean()
    df['MA_50'] = df['close'].rolling(window = 50).mean()
    
    
    df['L14'] = df['min'].rolling(window=14).min()
    df['H14'] = df['max'].rolling(window=14).max()
    df['%K'] = 100*((df['close'] - df['L14']) / (df['H14'] - df['L14']) )
    df['%D'] = df['%K'].rolling(window=3).mean()
    
    df['EMA_20'] = df['close'].ewm(span = 20, adjust = False).mean()
    df['EMA_50'] = df['close'].ewm(span = 50, adjust = False).mean()
    
    rsi_period = 14 
    chg = df['close'].diff(1)
    gain = chg.mask(chg<0,0)
    df['gain'] = gain
    loss = chg.mask(chg>0,0)
    df['loss'] = loss
    avg_gain = gain.ewm(com = rsi_period - 1, min_periods = rsi_period).mean()
    avg_loss = loss.ewm(com = rsi_period - 1, min_periods = rsi_period).mean()
    
    df['avg_gain'] = avg_gain
    df['avg_loss'] = avg_loss
    rs = abs(avg_gain/avg_loss)
    df['rsi'] = 100-(100/(1+rs))
    
    
    df = df.drop(columns = {'open','min','max','avg_gain','avg_loss','L14','H14','gain','loss'})
    
    df = df.dropna()
    df = df.fillna(method="ffill")
    df = df.dropna()
    
    df.sort_index(inplace = True)
    
    scaler = MinMaxScaler()
    indexes = df.index
    df_scaled = scaler.fit_transform(df)
    
    pred = pd.DataFrame(df_scaled,index = indexes)

    sequential_data = []
    prev_days = deque(maxlen = SEQ_LEN)            
    
    for i in pred.iloc[len(pred) -SEQ_LEN :len(pred)   , :].values:
        prev_days.append([n for n in i[:]])
        if len(prev_days) == SEQ_LEN:
            sequential_data.append([np.array(prev_days)])

    X = []

    for seq in sequential_data:
        X.append(seq)
    
    
    return np.array(X)



SEQ_LEN = 5  # how long of a preceeding sequence to collect for RNN
FUTURE_PERIOD_PREDICT = 2  # how far into the future are we trying to predict

ratio = 'EURUSD'

NAME = train_data() + '.model'
model = tf.keras.models.load_model(f'models/{NAME}')

iq = login()

i = 0
bid = True
bets = []
MONEY = 10000
bet_money = 1
trade = True

print("oi 0")
while(1):
    if i >= 10 and i % 2 == 0:
        NAME = train_data() + '.model'
        model = tf.keras.models.load_model(f'models/{NAME}')
        i = 0
    if datetime.datetime.now().second < 30 and i % 2 == 0: #GARANTE QUE ELE VAI APOSTAR NA SEGUNDA, POIS AQUI ELE JÁ PEGA OS DADOS DE UMA NA FRENTE,
        time_taker = time.time()
        pred_ready = preprocess_prediciton(iq)             #LOGO, ELE PRECISA DE TEMPO PRA ELABORAR A PREVISÃO ANTES DE ATINGIR OS 59 SEGUNDOS PRA ELE
        pred_ready = pred_ready.reshape(1,SEQ_LEN,pred_ready.shape[3])      #FAZER A APOSTA, ENÃO ELE VAI TENTAR PREVER O VALOR DA TERCEIRA NA FRENTE
        result = model.predict(pred_ready)
        print('probability of PUT or CALL : ',result)
        print(f'Time taken : {int(time.time()-time_taker)}')
        i = i + 1  

    if datetime.datetime.now().second == 59 and i%2 == 1:
        if result[0][0] > 0.5 :
            print('PUT')
            id = lower(iq,bet_money,ratio)
            i = i + 1   
            trade = True
        elif result[0][0] < 0.5 :
            print('CALL')
            id = higher(iq,bet_money,ratio) 
            i = i + 1
            trade = True
        else:
            trade = False
            i = i + 1
        #print("oi 2")
        if trade:
            time.sleep(2)
            
            #print(datetime.datetime.now().second)
            
            tempo = datetime.datetime.now().second
            while(tempo != 1): #ESPERA ATÉ SER 1 PRA PODER VER SE GANHOU OU NÃO
                tempo = datetime.datetime.now().second
                
            print(datetime.datetime.now().second)
            betsies = iq.get_optioninfo_v2(1)
            betsies = betsies['msg']['closed_options']
            
            for bt in betsies:
                bets.append(bt['win'])
            win = bets[-1:]
            print(win)
            if win == ['win']:
                #print(f'Balance : {get_balance(iq)}')
                bet_money = 1
                
            elif win == ['loose']:
                #print(f'Balance : {get_balance(iq)}')
                bet_money = bet_money * 3
                
            else:
                #print(f'Balance : {get_balance(iq)}')
                bets.append(0)
            print(bet_money)
            