#--------------------------------------------------------------------YOUTUBE DATA HARVESTING AND WAREHOUSING USING STREAMLIT--------------------------------#

#STREAMLIT AND PANDAS LIBRARY
import streamlit as st
from streamlit_option_menu import option_menu
from pyyoutube import Api
import pandas as pd

#MONGODB LIBRABRY
import pymongo
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi


#SQL LIBRARIES
import mysql.connector
import sqlalchemy
from sqlalchemy import create_engine
import pymysql

import re
import plotly.express as px
import isodate
#----------------------------------------------------------------------------------------------------------------------------------------------#
#ACCES THE API FROM YOUTUBE
api = Api(api_key="YOUR API KEY")

#establishing a connection in mongodb
client = pymongo.MongoClient("mongodb+srv://user:password@cluster0.s3tzdgl.mongodb.net/?retryWrites=true&w=majority")
dv = client.e12
collection=dv.youtube


# #establishing a connection in sql
connect = mysql.connector.connect(
host = "localhost",
user = "root",
password = ""
)
print(connect)
mycursor = connect.cursor(buffered=True)
#mycursor.execute("USE youtube_data")
engine = create_engine('mysql+pymysql://root:@localhost/youtube_data?charset=utf8mb4', echo=False)



#pushing youtube details into mongoDB
def push_to_mongo(pd_youtube):
    push_status = collection.insert_one(pd_youtube)
    return push_status


#extracting channel names from documnets pushed into mongoDB
def extract_channel_names():
    channel_names = []
    documents = collection.find()
    for document in documents:
        position_key = 1
        for key, value in document.items():
            if position_key % 2 == 0:
                channel_names.append(value)
                break
            position_key += 1
    return channel_names

#Extracting channel details
def get_channel_details(channel_id):
    
    # channel
    channel = api.get_channel_info(channel_id=channel_id)
    channel_name = channel.items[0].to_dict()["snippet"]["title"]
    full_details_to_store = {}
    
    full_details_to_store[channel_name] = {
        "channel_name": channel_name,
        "channel_id": channel.items[0].to_dict()['id'],
        "video_count": channel.items[0].to_dict()['statistics']['videoCount'],
        "channel_views": channel.items[0].to_dict()['statistics']['viewCount'],
        "channel_description": channel.items[0].to_dict()["snippet"]["description"],
        
        "playlists": {},
        "videos": {},
        "comments": {}
    }
    
    # playlist
    playlists_by_channel = api.get_playlists(channel_id=channel_id, count=5) 
    for playlist in playlists_by_channel.items:
        full_details_to_store[channel_name]["playlists"][playlist.to_dict()["id"]] = {
            "playlist_id": playlist.to_dict()["id"],
            "channel_id": playlist.to_dict()['snippet']['channelId'],
            "playlist_title": playlist.to_dict()["snippet"]["title"],
            "videos": []
        }
    
    # videos
    playlist_dict = {}
    for i in [i.id for i in playlists_by_channel.items]:
        if i not in playlist_dict:
            playlist_dict[i] = api.get_playlist_items(playlist_id=i, count=5)
    for key, val in playlist_dict.items():
        for videos in val.items: 
            full_details_to_store[channel_name]["playlists"][key]["videos"] += [videos.contentDetails.videoId]
    for key, val in playlist_dict.items():
        for i in val.items:
            vid_dict = {}
            if i.contentDetails.videoId not in full_details_to_store[channel_name]["videos"]:
                video_details = api.get_video_by_id(video_id=i.contentDetails.videoId)
                if len(video_details.items) > 0:
                    video_dict = video_details.items[0].to_dict()
                    vid_dict["video_id"] = i.contentDetails.videoId
                    vid_dict["channel_id"] = channel_id
                    vid_dict["video_name"] = video_dict['snippet']['title']
                    vid_dict["video_description"] = video_dict['snippet']['description']
                    vid_dict["published_at"] = video_dict['snippet']['publishedAt']
                    vid_dict["view_count"] = video_dict['statistics']['viewCount']
                    vid_dict["like_count"] = video_dict['statistics']['likeCount']
                    vid_dict["dislike_count"] = video_dict['statistics']['dislikeCount']
                    vid_dict["comment_count"] = video_dict['statistics']['commentCount']
                    vid_dict["duration"] = video_dict['contentDetails']['duration']
                    vid_dict["thumbnail"] = video_dict['snippet']['thumbnails']
                    vid_dict["caption_status"] = video_dict['contentDetails']['caption']
                    vid_dict["comments"] = []
                    full_details_to_store[channel_name]["videos"][i.contentDetails.videoId] = vid_dict

    
    # Define a function to convert duration
    def convert_duration(duration):
            regex = r'PT(\d+H)?(\d+M)?(\d+S)?'
            match = re.match(regex, duration)
            if not match:
                return '00:00:00'
            hours, minutes, seconds = match.groups()
            hours = int(hours[:-1]) if hours else 0
            minutes = int(minutes[:-1]) if minutes else 0
            seconds = int(seconds[:-1]) if seconds else 0
            total_seconds = hours * 3600 + minutes * 60 + seconds
            return '{:02d}:{:02d}:{:02d}'.format(int(total_seconds / 3600), int((total_seconds % 3600) / 60), int(total_seconds % 60))
   
    
    
    
    
    
    # comment
    for video_id in full_details_to_store[channel_name]["videos"]:
        com_dict = {}
        comment_dict = api.get_comment_threads(video_id=video_id, count=5)
        for comment in comment_dict.items:
            video_id = comment.to_dict()['snippet']['videoId']
            comment_id = comment.to_dict()['snippet']['topLevelComment']['id']
            full_details_to_store[channel_name]["videos"][video_id]["comments"] += [comment_id]
            com_dict["channel_id"] = channel_id
            com_dict["Video_id"] = video_id
            com_dict["Comment_Id"] = comment_id
            com_dict["Comment_Text"] = comment.to_dict()['snippet']['topLevelComment']['snippet']['textOriginal']
            com_dict["Comment_Author"] = comment.to_dict()['snippet']['topLevelComment']['snippet']['authorDisplayName']
            com_dict["Comment_PublishedAt"] = comment.to_dict()['snippet']['topLevelComment']['snippet']['publishedAt']
            full_details_to_store[channel_name]["comments"][comment_id] = com_dict
   
    return {"channel_name": full_details_to_store[channel_name]["channel_name"], "data": full_details_to_store[channel_name]}


#Migrating channel details data from mongodb to SQL
def migrate_to_sql(channel_name):

    channel_data = collection.find({"channel_name": channel_names})[0]

    channel_df = pd.DataFrame([[channel_data["data"]["channel_name"], channel_data["data"]["channel_id"], channel_data["data"]["video_count"] , channel_data["data"]["channel_views"], channel_data["data"]["channel_description"]]], 
                                columns=["Channel_Name", "Channel_Id","Video_Count" ,"Channel_Views", "Channel_Description"])
    channel_df.to_sql('channel', engine, if_exists='append', index=False, 
                        dtype={"Channel_Name": sqlalchemy.types.VARCHAR(length=225),
                            "Channel_Id": sqlalchemy.types.VARCHAR(length=225),
                            "Channel_Views": sqlalchemy.types.BigInteger,
                            "Channel_Description": sqlalchemy.types.TEXT})

    playlist = []
    for key, val in channel_data["data"]["playlists"].items():
        playlist.append([val["playlist_id"], val["channel_id"], val["playlist_title"]])
    playlist_df = pd.DataFrame(playlist, columns=["Playlist_Id", "Channel_Id", "Playlist_Title"])
    playlist_df.to_sql('playlist', engine, if_exists='append', index=False, 
                        dtype={"Playlist_Id": sqlalchemy.types.VARCHAR(length=225),
                            "Channel_Id": sqlalchemy.types.VARCHAR(length=225),
                            "Playlist_Title": sqlalchemy.types.VARCHAR(length=225)})

    video = []
    for key, val in channel_data["data"]["videos"].items():
        video.append([val["video_id"], val['channel_id'], val["video_name"], val["video_description"],val["published_at"],val["view_count"],val["like_count"],val["dislike_count"],val["comment_count"],val["duration"],val["caption_status"]])
    video_df = pd.DataFrame(video, columns=["Video_Id", 'Channel_Id' ,"Video_Name", "Video_Description",'Published_date','View_Count','Like_Count','Dislike_Coun','Comment_Count','Duration','Caption_Status'])
    video_df.to_sql('video', engine, if_exists='append', index=False, 
                        dtype={'Video_Id': sqlalchemy.types.VARCHAR(length=225),
                            'Channel_Id': sqlalchemy.types.VARCHAR(length=225),
                            'Video_Name': sqlalchemy.types.VARCHAR(length=225),
                            'Video_Description': sqlalchemy.types.TEXT,
                            'Published_date': sqlalchemy.types.String(length=50),
                            'View_Count': sqlalchemy.types.BigInteger,
                            'Like_Count': sqlalchemy.types.BigInteger,
                            'Dislike_Coun': sqlalchemy.types.INT,
                            'Comment_Count': sqlalchemy.types.INT,
                            'Duration': sqlalchemy.types.VARCHAR(length=1024),
                            'Caption_Status': sqlalchemy.types.VARCHAR(length=225)})
    video_df['durationSecs'] = video_df['Duration'].apply(lambda x: isodate.parse_duration(x))
    video_df['durationSecs'] = video_df['durationSecs'].astype('timedelta64[s]')
    
    
    
    comment = []
    for key, val in channel_data["data"]["comments"].items():
        comment.append([val["Video_id"],val['channel_id'] , val["Comment_Id"], val["Comment_Text"],val["Comment_Author"],val["Comment_PublishedAt"]])
    comment_df = pd.DataFrame(comment, columns=['Video_Id','Channel_Id','Comment_Id','Comment_Text','Comment_Author','Comment_Published_date'])
    comment_df.to_sql('comment', engine, if_exists='append', index=False,
                        dtype={'Video_Id': sqlalchemy.types.VARCHAR(length=225),
                            'Channel_Id': sqlalchemy.types.VARCHAR(length=225),
                            'Comment_Id': sqlalchemy.types.VARCHAR(length=225),
                            'Comment_Text': sqlalchemy.types.TEXT,
                            'Comment_Author': sqlalchemy.types.VARCHAR(length=225),
                            'Comment_Published_date': sqlalchemy.types.String(length=50)})
    return




#---------------------------------------------------------------| CREATE DASHBOARD USING STREAMLIT |-------------------------------------------------#
#CREATE NAVBAR FOR EACH PROCESS
st.set_page_config(layout='wide')
def streamlit_menu(example=2):
    if example == 2:
        
        selected = option_menu(
            menu_title="YOUTUBE DATA HARVESTING AND WAREHOUSING",  # required
            options=["ABOUT THE PROJECT","DATA COLLECTION","SELECT AND STORE", "MIGRATION OF DATA","DATA ANALYSIS"],  # required
            icons=["box-seam","basket","bank", "easel","graph-up-arrow"],  # optional
            menu_icon="youtube",  # optional
            default_index=0,  # optional
            orientation="horizontal",
        )
        return selected


#Page Contents
selected = streamlit_menu(example=2)

if selected == "ABOUT THE PROJECT":
    st.title("EXPLANATION ABOUT PROJECT:")
    st.write("1.This project Collects the data from youtube using youtube api and get stored the data in mongodb and migrate through sql and visualised")
    st.write("2.The streamlit Application allows the users to access and analyze data from multiple YouTube channels.")
    st.write('3.This application allows the user to give a YouTube channel ID as input and retrieves the relevant data. Able to collect data for multiple YouTube channels and store them in a database by just clicking a button. ') 
    st.write('4.By Selecting a channel , we could migrate the data from Mongo Database to SQL, to retrieve the relevant youtube Channel information like video comments , likes.')
    st.title("HOW TO GET CHANNEL ID FROM YOUTUBE:")
    st.write("#")
    st.write('1. Go to your favorite youtube channel, **right click** on the channel screen. Click on the **View Page Source** option.')
    st.write('2. Press Ctrl+F , search for **https://www.youtube.com/channel/** in source page. The **channel ID** will appear after the link.')
    st.write('3. Paste the Channel ID in the search field of **Select and store**.')
    st.write('FIRST IMAGE')
    st.image('channelpage.png')
    st.write('SECOND IMAGE')
    st.image('channelid.png')
    st.write('THIRD IMAGE')
    st.image('flowchart.png')

if selected == "DATA COLLECTION":
    st.write("THIS PAGE PROVIDE COLLECTION OF CHANNEL NAME AND CHANNEL ID")
    data = {
                 'CHANNEL NAME': ['SEE SAW','MICSET','PARITHABANGAL','BLACK SHEEP','FINALLY','MADRASI','ERUMA SAANI','SOTHANAIGAL','UNAKKENNAPAA','MADRASCENTRAL'],
                 'CHANNEL ID': ['UCMyi2FZAUNLFDUE8ZIf7YOQ', 'UC5EQWvy59VeHPJz8mDALPxg','UCueYcgdqos0_PzNOq81zAFg','UCzh5hQc_O3r3xjh9sXrM7-A','UCi3o8sgPl4-Yt501ShuiEgA','UCUEQ2_uz-3p9aEhvwlK3VdA','UCPyFYlqbkxkWX_dWCg0eekA','UCD1CuflSWxeAGVOwicubsWw','UCKoQ57VjNbcx9LEfVvTLBdQ','UCGBnz-FR3qaowYsyIEh2-zw']
                   }
    df = pd.DataFrame(data)
    st.table(df)


if selected == "SELECT AND STORE":
    Channel_id = st.text_input("**Enter a Channel ID**:", key="Channel_id", value="")
    st.write("(Example : UCzh5hQc_O3r3xjh9sXrM7-A)")
    st.write("#")
    if st.button('STORE IN MONGODB'):
        channel_info = get_channel_details(Channel_id)
        pushed_to_mongo = push_to_mongo(channel_info)
        if pushed_to_mongo.acknowledged:
            st.markdown('<p style="font-weight:bold;color:violet;">DATA INSERTED IN MONGODB</p>', unsafe_allow_html=True)
        else:
            st.markdown('<p style="font-weight:bold;color:red;">Error: DATA NOT INSERTED IN MONGODB</p>', unsafe_allow_html=True)
       

if selected == "MIGRATION OF DATA":
     channel_name = extract_channel_names()
     channel_names = st.selectbox("**SELECT THE CHANNEL NAME**:",channel_name)
     st.write("#")
     if st.button('MIGRATE TO SQL'):
        migrate_to_sql(channel_names)
        collection.delete_one({'channel_name': channel_names})
        st.markdown('<p style="font-weight:bold;color:violet;">MIGRATED TO SQL</p>', unsafe_allow_html=True)


if selected == "DATA ANALYSIS":
    st.title('HERE YOU CAN ANALYSE THE DATA')
    Questions = ["1. What are the names of all the videos and their corresponding channels",
             "2. Which channels have the most number of videos, and how many videos do they have",
             "3. What are the top 10 most viewed videos and their respective channels",
             "4. How many comments were made on each video, and what are their corresponding video names",
             "5. Which videos have the highest number of likes, and what are their corresponding channel names",
             "6. what is the total number of likes and dislikes of each video, and what are their corresponding video names",
             "7. what is the total number of views for each channel, and what are their corresponding channel names",
             "8. what is the names of all the channels that have published videos in the year 2022",
             "9. what is the average duration of all videos in each channel, and what are their corresponding channel names",
             "10. which videos have the highest number of comments,and what are their corresponding channel names"
             ]
    input_question = st.selectbox("**SELECT YOUR QUESTION TO GET DATA**:", Questions)
    retrieve_answer_from_sql = pymysql.connect(host="localhost", user="root", password="", db='youtube_data')
    cursor = retrieve_answer_from_sql.cursor()




    if input_question == '1. What are the names of all the videos and their corresponding channels':
        cursor.execute("""SELECT channel.Channel_Name , video.Video_Name FROM channel JOIN video ON video.Channel_Id = channel.Channel_Id""")
        result = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]  
        df_1 = pd.DataFrame(result, columns=columns).reset_index()
        df_1.index += 1
        st.write(df_1)

    elif input_question == '2. Which channels have the most number of videos, and how many videos do they have':
        col1,col2 =st.columns(2)
        with col1:
         cursor.execute("SELECT Channel_Name, Video_Count FROM channel ORDER BY Video_Count DESC;")
         result = cursor.fetchall()
         df_2 = pd.DataFrame(result, columns=['Channel_Name', 'Video_Count']).reset_index()
         df_2.index += 1
         st.write(df_2)
       
        with col2:
         fig_vc = px.bar(df_2, y='Video_Count', x='Channel_Name', text_auto='.2s', title="MOST NUMBER OF VIDEOS", )
         fig_vc.update_traces(textfont_size=16,marker_color='#E6064A')
         fig_vc.update_layout(title_font_color='#1308C2 ',title_font=dict(size=25))
         st.plotly_chart(fig_vc,use_container_width=True)     


    elif input_question == '3. What are the top 10 most viewed videos and their respective channels':
        cursor.execute("with channel_rank_data as ( SELECT channel.Channel_Name as channel_name, video.Video_Name as video_name, video.View_Count, row_number() over (partition by channel_name order by video.View_Count desc) as video_rank FROM channel JOIN video ON video.Channel_Id = channel.Channel_Id ) select * from channel_rank_data where video_rank <=10;") 
        result = cursor.fetchall()
        df_3 = pd.DataFrame(result, columns=['Channel_Name','Video_Name', 'View_Count', 'Rank']).reset_index()
        df_3.index += 1
        st.write(df_3)
    
    
    elif input_question == '4. How many comments were made on each video, and what are their corresponding video names':
        cursor.execute("SELECT channel.Channel_Name ,COUNT(*) AS Comment_Count ,video.Video_Name FROM video JOIN comment ON video.Video_Id = comment.Video_Id JOIN channel ON video.Channel_Id = channel.Channel_Id GROUP BY video.Video_Id, video.Video_Name, channel.Channel_Name;")
        result = cursor.fetchall()
        df_4 = pd.DataFrame(result, columns=['Channel_Name','Comment_Count', 'Video_Name']).reset_index()
        df_4.index += 1
        st.write(df_4)


    elif input_question == '5. Which videos have the highest number of likes, and what are their corresponding channel names':
        cursor.execute("SELECT channel.Channel_Name, video.Like_Count, video.Video_Name FROM video JOIN channel ON video.Channel_Id = channel.Channel_Id ORDER BY video.Like_Count DESC LIMIT 10;")
        result = cursor.fetchall()
        df_5 = pd.DataFrame(result, columns=['Channel_Name', 'Like_Count','Video_Name']).reset_index()
        df_5.index += 1
        st.write(df_5)
    
    elif input_question == '6. what is the total number of likes and dislikes of each video, and what are their corresponding video names':
        st.write(' In November 2021, YouTube removed the public dislike count from all of its videos.')
        cursor.execute("SELECT channel.Channel_Name, video.Like_Count, video.Video_Name, video.Dislike_Coun FROM video JOIN channel ON video.Channel_Id = channel.Channel_Id ORDER BY video.Dislike_Coun DESC;")
        result = cursor.fetchall()
        df_6 = pd.DataFrame(result, columns=['Channel_Name', 'Like_Count','Video_Name','Dislike_Coun']).reset_index()
        df_6.index += 1
        st.write(df_6)

    elif input_question == '7. what is the total number of views for each channel, and what are their corresponding channel names':
        col1,col2 =st.columns(2)
        with col1:
         cursor.execute("SELECT Channel_Name, Channel_Views FROM channel ORDER BY Channel_Views DESC;")
         result = cursor.fetchall()
         df_7 = pd.DataFrame(result, columns=['Channel_Name', 'Total number of views']).reset_index()
         df_7.index += 1
         st.write(df_7) 
        
         with col2:
          fig_vc = px.line(df_7, y='Total number of views', x='Channel_Name', title="TOTAL VIEWS OF EACH CHANNEL", )
          fig_vc.update_traces(textfont_size=16,marker_color='#f562fa')
          fig_vc.update_layout(title_font_color='#1308C2 ',title_font=dict(size=25))
          st.plotly_chart(fig_vc,use_container_width=True) 
    
    
    elif input_question == '8. what is the names of all the channels that have published videos in the year 2022':
        cursor.execute("SELECT channel.Channel_Name, video.Video_Name, video.Published_date FROM channel JOIN playlist ON channel.Channel_Id = playlist.Channel_Id JOIN video ON playlist.Playlist_Id = video.Playlist_Id  WHERE EXTRACT(YEAR FROM Published_date) = 2022;")
        result = cursor.fetchall()
        df_8 = pd.DataFrame(result, columns=['Channel_Name', 'Video_Name','Year 2022 only']).reset_index()
        df_8.index += 1
        st.write(df_8)

    elif input_question == '9. what is the average duration of all videos in each channel, and what are their corresponding channel names':
        cursor.execute("SELECT channel.Channel_Name, TIME_FORMAT(SEC_TO_TIME(AVG(TIME_TO_SEC(TIME(video.Duration)))), '%H:%i:%s') AS duration  FROM channel JOIN playlist ON channel.Channel_Id = playlist.Channel_Id JOIN video ON playlist.Playlist_Id = video.Playlist_Id GROUP by Channel_Name ORDER BY duration DESC ;")
        result = cursor.fetchall()
        df_9 = pd.DataFrame(result, columns=['Channel_Name', 'Average duration of videos (HH:MM:SS)']).reset_index()
        df_9.index += 1
        st.write(df_9)

    elif input_question == '10. which videos have the highest number of comments,and what are their corresponding channel names':
        cursor.execute("SELECT channel.Channel_Name, video.Video_Name, video.Comment_Count FROM video JOIN channel ON video.Channel_Id = channel.Channel_Id ORDER BY video.Comment_Count DESC LIMIT 10;")
        result = cursor.fetchall()
        df_10 = pd.DataFrame(result, columns=['Channel_Name','Video_Name','Comment_Count']).reset_index()
        df_10.index += 1
        st.write(df_10)    

          

