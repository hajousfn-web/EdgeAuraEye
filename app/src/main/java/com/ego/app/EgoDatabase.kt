package com.ego.app

import android.content.Context
import androidx.room.*

// 1. هيكل الجدول (Entity) اللي غا يخزن الداتا
@Entity(tableName = "ego_logs")
data class EgoLogEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val latitude: Double,
    val longitude: Double,
    val speed: Float,
    val distance: Float,
    val timestamp: Long = System.currentTimeMillis()
)

// 2. الواجهة ديال العمليات (DAO) لتخزين وقراءة الداتا
@Dao
interface EgoDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertLog(log: EgoLogEntity)

    @Query("SELECT * FROM ego_logs ORDER BY timestamp DESC")
    suspend fun getAllLogs(): List<EgoLogEntity>

    @Query("DELETE FROM ego_logs WHERE id = :id")
    suspend fun deleteLog(id: Long)

    @Query("DELETE FROM ego_logs")
    suspend fun clearLogs()
}

// 3. قاعدة البيانات المحلية (Database Instance)
@Database(entities = [EgoLogEntity::class], version = 1)
abstract class EgoDatabase : RoomDatabase() {
    abstract fun egoDao(): EgoDao

    companion object {
        @Volatile
        private var INSTANCE: EgoDatabase? = null

        fun getDatabase(context: Context): EgoDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    EgoDatabase::class.java,
                    "ego_database"
                ).build()
                INSTANCE = instance
                instance
            }
        }
    }
}