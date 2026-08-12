package com.example.sdkdemo.util;

import androidx.annotation.NonNull;

import com.volcengine.common.util.CompatPredicate;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.List;

public class CollectionUtil {

    public static <T, R> List<R> map(Collection<T> list, Convertor<T, R> convertor) {
        if (list == null) {
            list = Collections.emptyList();
        }
        ArrayList<R> result = new ArrayList<R>(list.size());
        for (T t : list) {
            result.add(convertor.convert(t));
        }
        return result;
    }

    public static <T, R> List<R> map(T[] arr, Convertor<T, R> convertor) {
        ArrayList<R> result = new ArrayList<R>(arr.length);
        for (T t : arr) {
            result.add(convertor.convert(t));
        }
        return result;
    }

    public static JSONArray toJsonArray(@NonNull List<String> strings){
        JSONArray array = new JSONArray();
        for (String string : strings) {
            array.put(string);
        }
        return array;
    }

    public static <T> JSONArray toJsonArray(@NonNull List<T> list, @NonNull Convertor<T, JSONObject> convertor) {
        JSONArray array = new JSONArray();
        for (T t : list) {
            array.put(convertor.convert(t));
        }
        return array;
    }

    public interface Convertor<T, R> {
        R convert(T t);
    }

    public static boolean isEmpty(List<?> list) {
        return list == null || list.isEmpty();
    }


    public static <T> boolean any(Collection<T> collection, CompatPredicate<T> predicate) {
        if (collection == null) {
            return false;
        }
        for (T t : collection) {
            if (predicate.test(t)) {
                return true;
            }
        }
        return false;
    }

    public static <T> T find(Collection<T> collection, CompatPredicate<T> predicate) {
        if (collection == null) {
            return null;
        }
        for (T t : collection) {
            if (predicate.test(t)) {
                return t;
            }
        }
        return null;
    }
}
