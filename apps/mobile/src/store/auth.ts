import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const memStore: Record<string, string> = {};

async function get(key: string): Promise<string | null> {
  if (Platform.OS === "web") return memStore[key] ?? null;
  return SecureStore.getItemAsync(key);
}

async function set(key: string, value: string): Promise<void> {
  if (Platform.OS === "web") { memStore[key] = value; return; }
  await SecureStore.setItemAsync(key, value);
}

async function del(key: string): Promise<void> {
  if (Platform.OS === "web") { delete memStore[key]; return; }
  await SecureStore.deleteItemAsync(key);
}

export async function getToken(type: "access" | "refresh"): Promise<string | null> {
  return get(`${type}_token`);
}

export async function setToken(type: "access" | "refresh", token: string): Promise<void> {
  await set(`${type}_token`, token);
}

export async function getOwnerId(): Promise<string | null> {
  return get("owner_id");
}

export async function setOwnerId(id: string): Promise<void> {
  await set("owner_id", id);
}

export async function clearAll(): Promise<void> {
  await Promise.all([
    del("access_token"),
    del("refresh_token"),
    del("owner_id"),
  ]);
}
